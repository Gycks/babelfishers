from concurrent.futures import ThreadPoolExecutor

import pytest

from babelfishers.core.tm_store import TMStore
from babelfishers.models.translations import StoreStats


@pytest.fixture
def store(tmp_path):
    return TMStore(tmp_path / "tm.sqlite3")


def _insert_row(store, key, translated="translated", engine="deepl", created_at=0, last_used=0):
    with store._write_lock, store._conn() as conn:
        conn.execute(
            "INSERT INTO translation_memory (key, translated, engine, created_at, last_used) VALUES (?, ?, ?, ?, ?)",
            (key, translated, engine, created_at, last_used),
        )


class TestTMStoreLookupAndStore:
    def test_lookup_returns_none_for_a_key_never_stored(self, store):
        assert store.lookup("Hello", "en", "fr") is None

    def test_store_then_lookup_round_trips_the_translation(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        assert store.lookup("Hello", "en", "fr") == "Bonjour"

    def test_lookup_is_scoped_by_target_locale(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.store("Hello", "en", "de", "Hallo", "deepl")

        assert store.lookup("Hello", "en", "fr") == "Bonjour"
        assert store.lookup("Hello", "en", "de") == "Hallo"

    def test_lookup_is_scoped_by_source_locale(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        assert store.lookup("Hello", "es", "fr") is None

    def test_store_upsert_updates_translated_and_engine_but_preserves_created_at(self, store, monkeypatch):
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 1000)
        store.store("Hello", "en", "fr", "Bonjour", "deepl")

        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 2000)
        store.store("Hello", "en", "fr", "Salut", "google-translate")

        with store._conn() as conn:
            row = conn.execute("SELECT translated, engine, created_at, last_used FROM translation_memory").fetchone()

        assert row == ("Salut", "google-translate", 1000, 2000)

    def test_store_upsert_bumps_last_used_on_conflict(self, store, monkeypatch):
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 1000)
        store.store("Hello", "en", "fr", "Bonjour", "deepl")

        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 5000)
        store.store("Hello", "en", "fr", "Bonjour", "deepl")

        with store._conn() as conn:
            last_used = conn.execute("SELECT last_used FROM translation_memory").fetchone()[0]

        assert last_used == 5000


class TestTMStoreBatchAndBumping:
    def test_store_batch_persists_all_entries(self, store):
        store.store_batch(
            [
                ("Hello", "en", "fr", "Bonjour"),
                ("Bye", "en", "fr", "Au revoir"),
            ],
            "deepl",
        )

        assert store.lookup("Hello", "en", "fr") == "Bonjour"
        assert store.lookup("Bye", "en", "fr") == "Au revoir"

    def test_store_batch_upsert_behaves_like_individual_store_calls(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.store_batch([("Hello", "en", "fr", "Salut")], "google-translate")

        assert store.lookup("Hello", "en", "fr") == "Salut"

    def test_bump_last_used_for_keys_updates_only_the_given_keys(self, store, monkeypatch):
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 1000)
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.store("Bye", "en", "fr", "Au revoir", "deepl")

        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 9000)
        key = TMStore.make_key("Hello", "en", "fr")
        store.bump_last_used_for_keys([key])

        with store._conn() as conn:
            rows = dict(conn.execute("SELECT key, last_used FROM translation_memory").fetchall())

        other_key = TMStore.make_key("Bye", "en", "fr")
        assert rows[key] == 9000
        assert rows[other_key] == 1000

    def test_bump_last_used_for_keys_is_a_no_op_for_empty_list(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.bump_last_used_for_keys([])

        assert store.lookup("Hello", "en", "fr") == "Bonjour"

    def test_make_key_is_stable_and_locale_pair_sensitive(self):
        key = TMStore.make_key("Hello", "en", "fr")

        assert key == TMStore.make_key("Hello", "en", "fr")
        assert key != TMStore.make_key("Hello", "en", "de")
        assert key != TMStore.make_key("Hello", "es", "fr")
        assert key != TMStore.make_key("Bye", "en", "fr")


class TestTMStoreStats:
    def test_stats_on_empty_store_reports_zero_entries_and_none_timestamps(self, store):
        stats = store.stats()

        assert stats.total_entries == 0
        assert stats.oldest_entry_ts is None
        assert stats.newest_used_ts is None
        assert stats.by_engine == {}

    def test_stats_reports_total_entries_and_size_bytes(self, store, tmp_path):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.store("Bye", "en", "fr", "Au revoir", "deepl")

        stats = store.stats()

        assert stats.total_entries == 2
        assert stats.size_bytes == (tmp_path / "tm.sqlite3").stat().st_size

    def test_stats_groups_counts_by_engine(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.store("Bye", "en", "fr", "Au revoir", "deepl")
        store.store("Yes", "en", "fr", "Oui", "google-translate")

        stats = store.stats()

        assert stats.by_engine == {"deepl": 2, "google-translate": 1}


class TestStoreStatsSizeMb:
    def test_size_mb_converts_from_bytes(self):
        stats = StoreStats(
            total_entries=1,
            oldest_entry_ts=0,
            newest_used_ts=0,
            size_bytes=2 * 1024 * 1024,
            by_engine={},
        )
        assert stats.size_mb == 2.0


class TestTMStorePruning:
    def test_prune_older_than_deletes_entries_past_the_cutoff_and_keeps_recent_ones(self, store, monkeypatch):
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 10 * 86_400)
        _insert_row(store, "old-key", last_used=0)
        _insert_row(store, "recent-key", last_used=9 * 86_400)

        deleted = store.prune_older_than(5)

        assert deleted == 1
        with store._conn() as conn:
            remaining = {row[0] for row in conn.execute("SELECT key FROM translation_memory")}
        assert remaining == {"recent-key"}

    def test_prune_older_than_returns_zero_when_nothing_is_old_enough(self, store, monkeypatch):
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 10 * 86_400)
        _insert_row(store, "recent-key", last_used=9 * 86_400)

        assert store.prune_older_than(5) == 0

    def test_prune_by_engine_deletes_only_matching_engine_entries(self, store):
        _insert_row(store, "k1", engine="deepl")
        _insert_row(store, "k2", engine="google-translate")

        deleted = store.prune_by_engine("deepl")

        assert deleted == 1
        with store._conn() as conn:
            remaining = {row[0] for row in conn.execute("SELECT key FROM translation_memory")}
        assert remaining == {"k2"}

    def test_prune_keep_newest_retains_only_the_n_most_recently_used(self, store):
        _insert_row(store, "oldest", last_used=1)
        _insert_row(store, "middle", last_used=2)
        _insert_row(store, "newest", last_used=3)

        deleted = store.prune_keep_newest(2)

        assert deleted == 1
        with store._conn() as conn:
            remaining = {row[0] for row in conn.execute("SELECT key FROM translation_memory")}
        assert remaining == {"middle", "newest"}

    def test_prune_keep_newest_is_a_no_op_when_total_is_at_or_below_keep(self, store):
        _insert_row(store, "only-key", last_used=1)

        deleted = store.prune_keep_newest(5)

        assert deleted == 0
        with store._conn() as conn:
            remaining = {row[0] for row in conn.execute("SELECT key FROM translation_memory")}
        assert remaining == {"only-key"}

    def test_clear_removes_all_entries(self, store):
        store.store("Hello", "en", "fr", "Bonjour", "deepl")
        store.store("Bye", "en", "fr", "Au revoir", "deepl")

        store.clear()

        assert store.stats().total_entries == 0


class TestTMStoreConcurrency:
    def test_concurrent_store_calls_from_multiple_threads_do_not_lose_writes(self, store):
        n = 50

        def _store(i: int) -> None:
            store.store(f"text-{i}", "en", "fr", f"translated-{i}", "deepl")

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(_store, range(n)))

        stats = store.stats()
        assert stats.total_entries == n
        for i in range(n):
            assert store.lookup(f"text-{i}", "en", "fr") == f"translated-{i}"
