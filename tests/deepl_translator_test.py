import pytest
from deepl import AuthorizationException, QuotaExceededException, TextResult, TooManyRequestsException

from babelfishers.core.translators.deepl_translator import DeeplTranslator


def _result(text: str) -> TextResult:
    return TextResult(text=text, detected_source_lang="EN", billed_characters=len(text), model_type_used=None)


@pytest.fixture
def translator(monkeypatch) -> DeeplTranslator:
    monkeypatch.setenv("BF_DEEPL_API_KEY", "test-key")
    return DeeplTranslator()


class TestDeeplTranslatorTranslate:
    def test_sets_the_translated_text_without_writing_back(self, translator, make_unit):
        translator._translator.translate_text = lambda *args, **kwargs: _result("Bonjour")

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written == {}

    @pytest.mark.parametrize(
        ("source", "target", "source_lang", "target_lang"),
        [
            ("en", "fr", "EN", "FR-FR"),
            ("pt-BR", "en", "PT", "EN-US"),
            ("en-GB", "fil", "EN", "TL"),
            ("en", "es-MX", "EN", "ES-419"),
            ("zh", "pt", "ZH", "PT-PT"),
        ],
    )
    def test_sends_a_variant_only_as_the_target(self, translator, make_unit, source, target, source_lang, target_lang):
        calls = []
        translator._translator.translate_text = lambda *args, **kwargs: calls.append(kwargs) or _result("x")

        unit, _ = make_unit("Hello")
        translator.translate([unit], source, target)

        assert (calls[0]["source_lang"], calls[0]["target_lang"]) == (source_lang, target_lang)

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._translator.translate_text = lambda *args, **kwargs: calls.append(args)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert unit.translated_text == ""

    def test_raises_immediately_on_authorization_error(self, translator, make_unit):
        def fail(*args, **kwargs):
            raise AuthorizationException("bad key")

        translator._translator.translate_text = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(AuthorizationException):
            translator.translate([unit], "en", "fr")

    def test_raises_immediately_on_quota_exceeded(self, translator, make_unit):
        def fail(*args, **kwargs):
            raise QuotaExceededException("quota exceeded")

        translator._translator.translate_text = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(QuotaExceededException):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise TooManyRequestsException("slow down")
            return _result("Bonjour")

        translator._translator.translate_text = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert unit.translated_text == "Bonjour"
