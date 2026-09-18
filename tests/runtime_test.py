import json
import logging
from pathlib import Path

import pytest

from babelfishers.core.runtime import Runtime
from babelfishers.core.translators.registry import translators_registry
from babelfishers.core.translators.translator import Translator
from babelfishers.models.app_config import AppConfig
from babelfishers.models.engine import Engine
from babelfishers.models.run_lock import StaleReason
from babelfishers.models.translation_resource import TranslationResource


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def write_json(tmp_path):
    def _write(relative_path: str, content: dict) -> Path:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    return _write


def _resources(paths_data: dict) -> list[TranslationResource]:
    return TranslationResource.load("en", "json", paths_data)


def _config(resources, target_locales, engine=Engine.DeepL, glossary=None) -> AppConfig:
    return AppConfig(
        source_locale="en",
        target_locales=target_locales,
        resources=resources,
        translation_engine=engine,
        glossary=glossary,
    )


def _register(monkeypatch, engine, transform=None, call_log=None, fail_targets=frozenset()):
    class _Translator(Translator):
        def __init__(self) -> None:
            super().__init__(engine)
            self._calls: dict[str, int] = {}

        def translate(self, data, source, target):
            if call_log is not None:
                call_log.append((engine, target))
            self._calls[target] = self._calls.get(target, 0) + 1
            if data and target in fail_targets:
                raise RuntimeError(f"simulated failure for {target}")
            for unit in data:
                if not unit.skip_translation:
                    unit.translated_text = transform(unit, target) if transform else unit.source_text
            return data

    monkeypatch.setitem(translators_registry, engine, _Translator)
    return _Translator


def _default_transform(unit, target):
    return f"[{target}] {unit.source_text}"


class TestRuntimeOrchestration:
    def test_orchestrate_translates_a_single_resource_to_all_target_locales(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr", "de"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert json.loads((tmp_path / "locales/fr/messages.json").read_text()) == {"greeting": "[fr] Hello"}
        assert json.loads((tmp_path / "locales/de/messages.json").read_text()) == {"greeting": "[de] Hello"}

    def test_orchestrate_skips_resource_with_no_matching_paths(self, write_json, tmp_path, monkeypatch, caplog):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        empty_resource = _resources({"paths": ["locales/[source]/does_not_exist_*.json"]})
        valid_resource = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(empty_resource + valid_resource, ["fr"])

        with caplog.at_level(logging.WARNING):
            Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert any("Entry has no valid paths" in r.message for r in caplog.records)
        assert json.loads((tmp_path / "locales/fr/messages.json").read_text()) == {"greeting": "[fr] Hello"}

    def test_orchestrate_handles_multiple_source_files_within_one_resource_independently(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        write_json("locales/en/errors.json", {"not_found": "Not found"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        resources = _resources({"paths": ["locales/[source]/*.json"]})
        config = _config(resources, ["fr"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert json.loads((tmp_path / "locales/fr/messages.json").read_text()) == {"greeting": "[fr] Hello"}
        assert json.loads((tmp_path / "locales/fr/errors.json").read_text()) == {"not_found": "[fr] Not found"}

    def test_orchestrate_shares_the_translation_memory_store_across_concurrent_jobs(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr"])
        db_storage = tmp_path / "store.sqlite"

        Runtime(config, db_storage=db_storage).orchestrate_translation_workflow()

        # second run: translator now always fails, so success proves the store was reused
        _register(monkeypatch, Engine.DeepL, fail_targets={"fr"})
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        resources2 = _resources({"paths": ["locales/[source]/messages.json"]})
        config2 = _config(resources2, ["fr"])
        Runtime(config2, db_storage=db_storage).orchestrate_translation_workflow()

        assert json.loads((tmp_path / "locales/fr/messages.json").read_text()) == {"greeting": "[fr] Hello"}

    def test_orchestrate_prefers_resource_specific_engine_over_the_global_engine(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        call_log = []
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, call_log=call_log)
        _register(monkeypatch, Engine.GoogleTranslate, transform=_default_transform, call_log=call_log)

        resources = _resources({
            "paths": [{"path": "locales/[source]/messages.json", "engine": "google-translate"}]
        })
        config = _config(resources, ["fr"], engine=Engine.DeepL)
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert call_log == [(Engine.GoogleTranslate, "fr")]

    def test_orchestrate_raises_when_one_locale_job_fails_but_other_locale_jobs_still_complete(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, fail_targets={"de"})

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr", "de"])

        with pytest.raises(ValueError, match="translation pipeline failed"):
            Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert json.loads((tmp_path / "locales/fr/messages.json").read_text()) == {"greeting": "[fr] Hello"}
        assert not (tmp_path / "locales/de/messages.json").exists()

    def test_orchestrate_with_many_locales_and_limited_workers_writes_correct_independent_content_for_each(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello", "farewell": "Bye"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        locales = [f"loc{i}" for i in range(8)]
        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, locales)
        Runtime(config, db_storage=tmp_path / "store.sqlite", max_workers=2).orchestrate_translation_workflow()

        for locale in locales:
            content = json.loads((tmp_path / f"locales/{locale}/messages.json").read_text())
            assert content == {"greeting": f"[{locale}] Hello", "farewell": f"[{locale}] Bye"}


class TestRuntimeRunLockSkipping:
    def test_second_run_skips_translation_when_nothing_changed(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        call_log = []
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, call_log=call_log)

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr", "es"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        call_log.clear()
        resources2 = _resources({"paths": ["locales/[source]/messages.json"]})
        config2 = _config(resources2, ["fr", "es"])
        Runtime(config2, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert call_log == []

    def test_retranslates_only_the_locale_whose_destination_file_was_deleted(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        call_log = []
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, call_log=call_log)

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr", "es"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        (tmp_path / "locales/fr/messages.json").unlink()
        call_log.clear()

        resources2 = _resources({"paths": ["locales/[source]/messages.json"]})
        config2 = _config(resources2, ["fr", "es"])
        Runtime(config2, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert call_log == [(Engine.DeepL, "fr")]
        assert json.loads((tmp_path / "locales/fr/messages.json").read_text()) == {"greeting": "[fr] Hello"}

    def test_retranslates_every_locale_when_the_source_file_content_changes(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        call_log = []
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, call_log=call_log)

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr", "es"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        write_json("locales/en/messages.json", {"greeting": "Hi there"})
        call_log.clear()

        resources2 = _resources({"paths": ["locales/[source]/messages.json"]})
        config2 = _config(resources2, ["fr", "es"])
        Runtime(config2, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert {target for _, target in call_log} == {"fr", "es"}

    def test_retranslates_every_locale_when_the_engine_changes(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        call_log = []
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, call_log=call_log)
        _register(monkeypatch, Engine.GoogleTranslate, transform=_default_transform, call_log=call_log)

        resources = _resources({"paths": ["locales/[source]/messages.json"]})
        config = _config(resources, ["fr", "es"], engine=Engine.DeepL)
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        call_log.clear()
        resources2 = _resources({"paths": ["locales/[source]/messages.json"]})
        config2 = _config(resources2, ["fr", "es"], engine=Engine.GoogleTranslate)
        Runtime(config2, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()

        assert {target for _, target in call_log} == {"fr", "es"}


class TestRuntimePlan:
    def test_plan_reports_every_locale_as_new_with_a_volume_estimate_before_any_run(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello", "farewell": "Bye"})
        call_log = []
        _register(monkeypatch, Engine.DeepL, transform=_default_transform, call_log=call_log)

        config = _config(_resources({"paths": ["locales/[source]/messages.json"]}), ["fr", "es"])
        plans = Runtime(config, db_storage=tmp_path / "store.sqlite").plan()

        assert {plan.locale for plan in plans} == {"fr", "es"}
        assert all(plan.stale_reason == StaleReason.NEW for plan in plans)
        assert all(plan.volume.units_to_translate == 2 for plan in plans)
        assert call_log == []

    def test_plan_writes_no_files_and_creates_no_state(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        config = _config(_resources({"paths": ["locales/[source]/messages.json"]}), ["fr"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").plan()

        assert not (tmp_path / "locales/fr").exists()
        assert not (tmp_path / "store.sqlite").exists()
        assert not (tmp_path / ".babelfishers").exists()

    def test_plan_reports_up_to_date_after_a_completed_run(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        config = _config(_resources({"paths": ["locales/[source]/messages.json"]}), ["fr", "es"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()
        plans = Runtime(config, db_storage=tmp_path / "store.sqlite").plan()

        assert all(plan.stale_reason is None for plan in plans)
        assert all(plan.volume is None for plan in plans)

    def test_plan_reports_only_the_deleted_locale_as_target_missing(self, write_json, tmp_path, monkeypatch):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)

        config = _config(_resources({"paths": ["locales/[source]/messages.json"]}), ["fr", "es"])
        Runtime(config, db_storage=tmp_path / "store.sqlite").orchestrate_translation_workflow()
        (tmp_path / "locales/fr/messages.json").unlink()

        plans = {plan.locale: plan for plan in Runtime(config, db_storage=tmp_path / "store.sqlite").plan()}

        assert plans["fr"].stale_reason == StaleReason.TARGET_MISSING
        assert plans["es"].stale_reason is None

    def test_plan_counts_cached_units_and_leaves_run_lock_untouched(
        self, write_json, tmp_path, monkeypatch
    ):
        write_json("locales/en/messages.json", {"greeting": "Hello"})
        _register(monkeypatch, Engine.DeepL, transform=_default_transform)
        db_storage = tmp_path / "store.sqlite"
        run_lock = tmp_path / ".babelfishers/run.lock"

        config = _config(_resources({"paths": ["locales/[source]/messages.json"]}), ["fr"])
        Runtime(config, db_storage=db_storage).orchestrate_translation_workflow()
        run_lock_before = run_lock.read_bytes()

        (tmp_path / "locales/en/messages.json").write_text(json.dumps({"greeting": "Hello"}, indent=2))
        plans = Runtime(config, db_storage=db_storage).plan()

        assert plans[0].stale_reason == StaleReason.CONTENT_CHANGED
        assert (plans[0].volume.cached_units, plans[0].volume.units_to_translate) == (1, 0)
        assert run_lock.read_bytes() == run_lock_before
