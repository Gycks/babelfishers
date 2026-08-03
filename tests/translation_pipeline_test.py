from pathlib import Path

import pytest

from babelfishers.core.tm_store import TMStore
from babelfishers.core.translation_pipeline import TranslationPipeline
from babelfishers.core.translators.registry import translators_registry
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary, GlossaryTerm
from babelfishers.models.translation_resource import TranslationResourceType as T
from babelfishers.models.translations import ParseResult, TranslationUnit


def _unit(key: str, source_text: str, written: dict) -> TranslationUnit:
    return TranslationUnit(
        unit_type=T.JSON,
        key=key,
        source_text=source_text,
        write_back=lambda v, key=key: written.__setitem__(key, v),
    )


def _parse_result(units: list[TranslationUnit], save=None) -> ParseResult:
    return ParseResult(source_path=Path("dummy.json"), units=units, save=save or (lambda dest: None), document={})


def _register(monkeypatch, engine: Engine, translator_cls: type) -> None:
    monkeypatch.setitem(translators_registry, engine, translator_cls)


def _echo_translator(engine: Engine, call_log: list | None = None):
    class _Translator(Translator):
        def __init__(self) -> None:
            super().__init__(engine)

        def translate(self, data, source, target):
            if call_log is not None:
                call_log.append((engine, len(data)))
            for unit in data:
                if not unit.skip_translation:
                    unit.translated_text = unit.source_text
            return data

    return _Translator


def _always_fail_translator(engine: Engine, call_log: list | None = None):
    class _Translator(Translator):
        def __init__(self) -> None:
            super().__init__(engine)

        def translate(self, data, source, target):
            if call_log is not None:
                call_log.append((engine, len(data)))
            raise RuntimeError("simulated translator failure")

    return _Translator


def _flaky_translator(engine: Engine, fail_times: int, call_log: list | None = None):
    class _Translator(Translator):
        def __init__(self) -> None:
            super().__init__(engine)
            self._calls = 0

        def translate(self, data, source, target):
            self._calls += 1
            if call_log is not None:
                call_log.append((engine, self._calls))
            if self._calls <= fail_times:
                raise RuntimeError("simulated transient failure")
            for unit in data:
                if not unit.skip_translation:
                    unit.translated_text = unit.source_text
            return data

    return _Translator


def _mangled_then_clean_translator(engine: Engine):
    class _Translator(Translator):
        def __init__(self) -> None:
            super().__init__(engine)
            self._calls = 0

        def translate(self, data, source, target):
            self._calls += 1
            for unit in data:
                if self._calls == 1:
                    unit.translated_text = unit.source_text.split("</gls>")[0]
                else:
                    unit.translated_text = unit.source_text
            return data

    return _Translator


@pytest.fixture
def tm_store(tmp_path):
    return TMStore(tmp_path / "tm.sqlite3")


class TestTranslationPipelineCacheHandling:
    def test_run_uses_cached_translation_without_calling_translator_for_a_full_cache_hit(
        self, tm_store, monkeypatch
    ):
        tm_store.store("Hello", "en", "fr", "Bonjour", "deepl")
        call_log = []
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL, call_log))

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written)])

        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written["k1"] == "Bonjour"

    def test_run_only_sends_cache_misses_to_the_translator_in_a_mixed_batch(self, tm_store, monkeypatch):
        tm_store.store("Hello", "en", "fr", "Bonjour", "deepl")
        call_log = []
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL, call_log))

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written), _unit("k2", "Bye", written)])

        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written["k1"] == "Bonjour"
        assert written["k2"] == "Bye"
        assert call_log == [(Engine.DeepL, 1)]

    def test_run_stores_newly_translated_units_but_not_cache_hits_into_the_store(self, tm_store, monkeypatch):
        tm_store.store("Hello", "en", "fr", "Bonjour", "deepl")
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL))

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written), _unit("k2", "Bye", written)])

        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert tm_store.lookup("Bye", "en", "fr") == "Bye"
        assert tm_store.stats().total_entries == 2

    def test_run_bumps_last_used_for_cache_hit_keys(self, tm_store, monkeypatch):
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 1000)
        tm_store.store("Hello", "en", "fr", "Bonjour", "deepl")
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL))

        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 9000)
        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        key = TMStore.make_key("Hello", "en", "fr")
        with tm_store._conn() as conn:
            last_used = conn.execute(
                "SELECT last_used FROM translation_memory WHERE key = ?", (key,)
            ).fetchone()[0]
        assert last_used == 9000


class TestTranslationPipelineWriteBackAndSave:
    def test_run_calls_write_back_with_final_text_for_both_hits_and_misses(self, tm_store, monkeypatch):
        tm_store.store("Hello", "en", "fr", "Bonjour", "deepl")
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL))

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written), _unit("k2", "Bye", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written == {"k1": "Bonjour", "k2": "Bye"}

    def test_run_calls_save_with_the_given_destination_path(self, tm_store, monkeypatch):
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL))

        save_calls = []
        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written)], save=lambda dest: save_calls.append(dest))

        destination = Path("/tmp/out.json")
        pipeline.run(parse_result, "en", "fr", destination)

        assert save_calls == [destination]


class TestTranslationPipelineEngineRetryAndSwitch:
    def test_retries_same_engine_before_switching_when_translator_fails_once_then_succeeds(
        self, tm_store, monkeypatch
    ):
        call_log = []
        _register(monkeypatch, Engine.DeepL, _flaky_translator(Engine.DeepL, fail_times=1, call_log=call_log))

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert call_log == [(Engine.DeepL, 1), (Engine.DeepL, 2)]
        assert written["k1"] == "Hello"

    def test_switches_to_next_engine_after_two_failed_attempts_on_first_engine(self, tm_store, monkeypatch):
        call_log = []
        _register(monkeypatch, Engine.DeepL, _always_fail_translator(Engine.DeepL, call_log))
        _register(monkeypatch, Engine.GoogleTranslate, _echo_translator(Engine.GoogleTranslate, call_log))

        written = {}
        pipeline = TranslationPipeline(
            [Engine.DeepL, Engine.GoogleTranslate], glossary=None, translation_store=tm_store
        )
        parse_result = _parse_result([_unit("k1", "Hello", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert call_log == [(Engine.DeepL, 1), (Engine.DeepL, 1), (Engine.GoogleTranslate, 1)]
        assert tm_store.stats().by_engine == {"google-translate": 1}

    def test_raises_when_all_engines_exhaust_their_retries(self, tm_store, monkeypatch):
        _register(monkeypatch, Engine.DeepL, _always_fail_translator(Engine.DeepL))
        _register(monkeypatch, Engine.GoogleTranslate, _always_fail_translator(Engine.GoogleTranslate))

        written = {}
        pipeline = TranslationPipeline(
            [Engine.DeepL, Engine.GoogleTranslate], glossary=None, translation_store=tm_store
        )
        parse_result = _parse_result([_unit("k1", "Hello", written)])

        with pytest.raises(ValueError, match="translation pipeline failed"):
            pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

    def test_retry_triggers_when_placeholder_restoration_fails_due_to_a_mangled_tag(self, tm_store, monkeypatch):
        _register(monkeypatch, Engine.DeepL, _mangled_then_clean_translator(Engine.DeepL))

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=None, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Hello %s", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written["k1"] == "Hello %s"


class TestTranslationPipelineGlossaryIntegration:
    def test_exact_match_non_translatable_glossary_term_bypasses_the_translator(self, tm_store, monkeypatch):
        call_log = []
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL, call_log))
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=glossary, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "Widget", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written["k1"] == "Gadget"

    def test_partial_match_glossary_term_round_trips_through_translation(self, tm_store, monkeypatch):
        _register(monkeypatch, Engine.DeepL, _echo_translator(Engine.DeepL))
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=glossary, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "I bought a Widget yesterday", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written["k1"] == "I bought a Gadget yesterday"

    def test_glossary_protection_is_not_corrupted_by_a_retry_after_a_transient_translator_failure(
        self, tm_store, monkeypatch
    ):
        """
        Regression test: a fresh GlossaryGuard is created for every retry attempt.
        If the dataset handed to it were the already-protected result of a prior
        failed attempt (instead of the original placeholder-protected baseline),
        the term would no longer be found, and the leftover <gls> wrapper would
        ship straight into the output unrestored.
        """
        _register(monkeypatch, Engine.DeepL, _flaky_translator(Engine.DeepL, fail_times=1))
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])

        written = {}
        pipeline = TranslationPipeline([Engine.DeepL], glossary=glossary, translation_store=tm_store)
        parse_result = _parse_result([_unit("k1", "I bought a Widget yesterday", written)])
        pipeline.run(parse_result, "en", "fr", Path("/tmp/out.json"))

        assert written["k1"] == "I bought a Gadget yesterday"
