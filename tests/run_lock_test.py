from concurrent.futures import ThreadPoolExecutor

import pytest

from babelfishers.core.run_lock import RunLockStore, compute_config_fingerprint
from babelfishers.models.app_config import AppConfig
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary, GlossaryTerm
from babelfishers.models.run_lock import RunLockEntry, StaleReason


@pytest.fixture
def store(tmp_path):
    return RunLockStore(tmp_path / "run.lock")


@pytest.fixture
def existing_destination(tmp_path):
    destination = tmp_path / "locales/fr/messages.json"
    destination.parent.mkdir(parents=True)
    destination.write_text("{}")
    return destination


def _entry(
    path="locales/en/messages.json",
    locale="fr",
    content_hash="hash-1",
    config_fingerprint="fp-1",
    last_run_at=1000,
) -> RunLockEntry:
    return RunLockEntry(
        path=path,
        locale=locale,
        content_hash=content_hash,
        config_fingerprint=config_fingerprint,
        last_run_at=last_run_at,
    )


def _config(target_locales, engine=Engine.DeepL, glossary=None) -> AppConfig:
    return AppConfig(
        source_locale="en", target_locales=target_locales, resources=[], translation_engine=engine, glossary=glossary
    )


class TestRunLockStoreLookupAndCreate:
    def test_lookup_returns_none_for_an_entry_never_created(self, store):
        assert store.lookup("locales/en/messages.json", "fr") is None

    def test_create_then_lookup_round_trips_the_entry(self, store):
        entry = _entry()
        store.create([entry])

        assert store.lookup(entry.path, entry.locale) == entry

    def test_create_is_a_no_op_for_empty_entries(self, store, tmp_path):
        store.create([])

        assert not (tmp_path / "run.lock").exists()

    def test_create_keeps_separate_entries_for_different_locales_of_the_same_path(self, store):
        store.create([_entry(locale="fr"), _entry(locale="es")])

        assert store.lookup("locales/en/messages.json", "fr") is not None
        assert store.lookup("locales/en/messages.json", "es") is not None

    def test_create_overwrites_an_existing_entry_for_the_same_path_and_locale(self, store):
        store.create([_entry(content_hash="hash-1")])
        store.create([_entry(content_hash="hash-2")])

        assert store.lookup("locales/en/messages.json", "fr").content_hash == "hash-2"

    def test_entries_persist_across_store_instances(self, tmp_path):
        destination = tmp_path / "run.lock"
        RunLockStore(destination).create([_entry()])

        reloaded = RunLockStore(destination)

        assert reloaded.lookup("locales/en/messages.json", "fr") == _entry()


class TestRunLockStoreIsStale:
    def test_is_stale_is_true_when_never_recorded(self, store, tmp_path):
        assert store.is_stale("locales/en/messages.json", "fr", "hash-1", "fp-1", tmp_path / "missing.json") is True

    def test_is_stale_is_false_when_hash_fingerprint_and_destination_all_match(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.is_stale("locales/en/messages.json", "fr", "hash-1", "fp-1", existing_destination) is False

    def test_is_stale_is_true_when_destination_file_is_missing(self, store, tmp_path):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert (
            store.is_stale("locales/en/messages.json", "fr", "hash-1", "fp-1", tmp_path / "does_not_exist.json") is True
        )

    def test_is_stale_is_true_when_content_hash_changed(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.is_stale("locales/en/messages.json", "fr", "hash-2", "fp-1", existing_destination) is True

    def test_is_stale_is_true_when_config_fingerprint_changed(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.is_stale("locales/en/messages.json", "fr", "hash-1", "fp-2", existing_destination) is True

    def test_is_stale_does_not_compare_destination_file_content(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])
        existing_destination.write_text('{"greeting": "manually edited"}')

        assert store.is_stale("locales/en/messages.json", "fr", "hash-1", "fp-1", existing_destination) is False


class TestRunLockStoreReplace:
    def test_replace_drops_every_previously_recorded_entry(self, store):
        store.create([_entry(locale="fr"), _entry(locale="de")])

        store.replace([_entry(locale="es")])

        assert store.lookup("locales/en/messages.json", "fr") is None
        assert store.lookup("locales/en/messages.json", "de") is None
        assert store.lookup("locales/en/messages.json", "es") is not None

    def test_replace_persists_so_a_new_store_instance_sees_only_the_replacement(self, store, tmp_path):
        store.create([_entry(locale="fr")])
        store.replace([_entry(locale="es")])

        reloaded = RunLockStore(tmp_path / "run.lock")

        assert reloaded.lookup("locales/en/messages.json", "fr") is None
        assert reloaded.lookup("locales/en/messages.json", "es") is not None

    def test_replace_with_no_entries_empties_the_store(self, store, tmp_path):
        store.create([_entry()])

        store.replace([])

        assert RunLockStore(tmp_path / "run.lock").lookup("locales/en/messages.json", "fr") is None


class TestRunLockStoreRemoveOrphans:
    def test_removes_entries_whose_path_and_locale_are_not_live_and_reports_how_many(self, store):
        store.create([_entry(locale="fr"), _entry(locale="de"), _entry(path="locales/en/old.json", locale="fr")])

        removed = store.remove_orphans({("locales/en/messages.json", "fr")})

        assert removed == 2
        assert store.lookup("locales/en/messages.json", "fr") is not None
        assert store.lookup("locales/en/messages.json", "de") is None
        assert store.lookup("locales/en/old.json", "fr") is None

    def test_removal_is_persisted(self, store, tmp_path):
        store.create([_entry(locale="fr"), _entry(locale="de")])

        store.remove_orphans({("locales/en/messages.json", "fr")})

        reloaded = RunLockStore(tmp_path / "run.lock")
        assert reloaded.lookup("locales/en/messages.json", "de") is None
        assert reloaded.lookup("locales/en/messages.json", "fr") is not None

    def test_is_a_no_op_that_does_not_touch_the_file_when_nothing_is_orphaned(self, store, tmp_path):
        store.create([_entry()])
        before = (tmp_path / "run.lock").stat().st_mtime_ns

        assert store.remove_orphans({("locales/en/messages.json", "fr")}) == 0
        assert (tmp_path / "run.lock").stat().st_mtime_ns == before

    def test_does_not_create_a_file_for_a_store_that_never_wrote_one(self, store, tmp_path):
        assert store.remove_orphans(set()) == 0
        assert not (tmp_path / "run.lock").exists()


class TestRunLockStoreDiscard:
    def test_drops_only_the_given_entries_and_persists(self, store, tmp_path):
        store.create([_entry(locale="fr"), _entry(locale="de")])

        store.discard([("locales/en/messages.json", "fr"), ("locales/en/unknown.json", "fr")])

        reloaded = RunLockStore(tmp_path / "run.lock")
        assert reloaded.lookup("locales/en/messages.json", "fr") is None
        assert reloaded.lookup("locales/en/messages.json", "de") is not None

    def test_does_not_create_a_file_when_nothing_was_recorded(self, store, tmp_path):
        store.discard([("locales/en/messages.json", "fr")])

        assert not (tmp_path / "run.lock").exists()


class TestRunLockStorePrune:
    def test_prune_removes_the_file_and_clears_entries(self, store, tmp_path):
        store.create([_entry()])

        assert store.prune() is True

        assert not (tmp_path / "run.lock").exists()
        assert store.lookup("locales/en/messages.json", "fr") is None

    def test_prune_reports_false_when_the_file_does_not_exist(self, store):
        assert store.prune() is False


class TestRunLockStoreConcurrency:
    def test_concurrent_create_calls_from_multiple_threads_do_not_lose_writes(self, store):
        n = 50

        def _create(i: int) -> None:
            store.create([_entry(locale=f"loc{i}", content_hash=f"hash-{i}")])

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(_create, range(n)))

        for i in range(n):
            assert store.lookup("locales/en/messages.json", f"loc{i}").content_hash == f"hash-{i}"


class TestComputeConfigFingerprint:
    def test_fingerprint_is_stable_for_the_same_config_values(self):
        first = compute_config_fingerprint(_config(["fr", "es"]))
        second = compute_config_fingerprint(_config(["fr", "es"]))

        assert first == second

    def test_fingerprint_is_unaffected_by_target_locales(self):
        assert compute_config_fingerprint(_config(["fr"])) == compute_config_fingerprint(_config(["fr", "es"]))

    def test_fingerprint_changes_when_engine_changes(self):
        assert compute_config_fingerprint(_config(["fr"], engine=Engine.DeepL)) != compute_config_fingerprint(
            _config(["fr"], engine=Engine.Anthropic)
        )

    def test_fingerprint_changes_when_glossary_changes(self):
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={})])

        assert compute_config_fingerprint(_config(["fr"], glossary=None)) != compute_config_fingerprint(
            _config(["fr"], glossary=glossary)
        )


class TestRunLockStoreStaleReason:
    def test_stale_reason_is_new_when_never_recorded(self, store, existing_destination):
        assert store.stale_reason("locales/en/messages.json", "fr", "hash-1", "fp-1", existing_destination) == (
            StaleReason.NEW
        )

    def test_stale_reason_is_none_when_hash_fingerprint_and_destination_all_match(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.stale_reason("locales/en/messages.json", "fr", "hash-1", "fp-1", existing_destination) is None

    def test_stale_reason_is_target_missing_when_only_the_destination_is_gone(self, store, tmp_path):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.stale_reason("locales/en/messages.json", "fr", "hash-1", "fp-1", tmp_path / "gone.json") == (
            StaleReason.TARGET_MISSING
        )

    def test_stale_reason_is_content_changed_when_the_source_hash_differs(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.stale_reason("locales/en/messages.json", "fr", "hash-2", "fp-1", existing_destination) == (
            StaleReason.CONTENT_CHANGED
        )

    def test_stale_reason_is_config_changed_when_only_the_fingerprint_differs(self, store, existing_destination):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.stale_reason("locales/en/messages.json", "fr", "hash-1", "fp-2", existing_destination) == (
            StaleReason.CONFIG_CHANGED
        )

    def test_stale_reason_prefers_target_missing_over_a_content_change(self, store, tmp_path):
        store.create([_entry(content_hash="hash-1", config_fingerprint="fp-1")])

        assert store.stale_reason("locales/en/messages.json", "fr", "hash-2", "fp-1", tmp_path / "gone.json") == (
            StaleReason.TARGET_MISSING
        )
