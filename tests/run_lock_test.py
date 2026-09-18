from concurrent.futures import ThreadPoolExecutor

import pytest

from babelfishers.core.run_lock import RunLockStore, compute_config_fingerprint
from babelfishers.models.app_config import AppConfig
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary, GlossaryTerm
from babelfishers.models.run_lock import RunLockEntry


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


class TestRunLockStorePrune:
    def test_prune_removes_the_file_and_clears_entries(self, store, tmp_path):
        store.create([_entry()])

        store.prune()

        assert not (tmp_path / "run.lock").exists()
        assert store.lookup("locales/en/messages.json", "fr") is None

    def test_prune_is_a_no_op_when_the_file_does_not_exist(self, store):
        store.prune()


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
