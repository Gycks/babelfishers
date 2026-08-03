import json
import logging
from pathlib import Path

import pytest

from babelfishers.core.runtime import Runtime
from babelfishers.core.translators.registry import translators_registry
from babelfishers.core.translators.translator import Translator
from babelfishers.models.app_config import AppConfig
from babelfishers.models.engine import Engine
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

        assert any("Bucket empty" in r.message for r in caplog.records)
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
