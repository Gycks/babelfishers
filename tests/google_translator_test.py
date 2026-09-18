import pytest
from google.genai import errors

from babelfishers.core.translators.google_translator import GoogleTranslator
from babelfishers.core.translators.llm_translator_toolkit import ModelTranslationResponse


def _response(parsed):
    return type("Response", (), {"parsed": parsed})()


@pytest.fixture
def translator(monkeypatch) -> GoogleTranslator:
    monkeypatch.setenv("BF_GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("BF_GOOGLE_MODEL_ID", "gemini-test")
    return GoogleTranslator()


class TestGoogleTranslatorTranslate:
    def test_writes_back_the_parsed_translation(self, translator, make_unit):
        translator._client.models.generate_content = lambda **kwargs: _response(
            ModelTranslationResponse(translation="Bonjour")
        )

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.models.generate_content = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise errors.ClientError(401, {"error": {"message": "bad key"}})

        translator._client.models.generate_content = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(errors.ClientError):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise errors.ClientError(429, {"error": {"message": "slow down"}})
            return _response(ModelTranslationResponse(translation="Bonjour"))

        translator._client.models.generate_content = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_when_the_response_has_no_parsed_translation(self, translator, make_unit):
        translator._client.models.generate_content = lambda **kwargs: _response(None)

        unit, _ = make_unit("Hello")
        with pytest.raises(ValueError, match="no parsable translation"):
            translator.translate([unit], "en", "fr")
