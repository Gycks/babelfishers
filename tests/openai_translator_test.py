import httpx
import openai
import pytest

from babelfishers.core.translators.openai_translator import OpenAITranslator


def _http_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code, headers=headers or {}, request=httpx.Request("POST", "https://api.openai.com/v1/x")
    )


def _response(translation: str | None = None, refusal: str | None = None):
    parsed = type("Parsed", (), {"translation": translation})() if translation is not None else None
    message = type("Message", (), {"refusal": refusal, "parsed": parsed})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice]})()


@pytest.fixture
def translator(monkeypatch) -> OpenAITranslator:
    monkeypatch.setenv("BF_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BF_OPENAI_MODEL_ID", "gpt-test")
    return OpenAITranslator()


class TestOpenAITranslatorTranslate:
    def test_sets_the_parsed_translation_without_writing_back(self, translator, make_unit):
        translator._client.chat.completions.parse = lambda **kwargs: _response("Bonjour")

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written == {}

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.chat.completions.parse = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert unit.translated_text == ""

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise openai.AuthenticationError("bad key", response=_http_response(401), body=None)

        translator._client.chat.completions.parse = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(openai.AuthenticationError):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise openai.RateLimitError("slow down", response=_http_response(429), body=None)
            return _response("Bonjour")

        translator._client.chat.completions.parse = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert unit.translated_text == "Bonjour"

    def test_raises_after_exhausting_rate_limit_retries(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)

        def always_fail(**kwargs):
            raise openai.RateLimitError("slow down", response=_http_response(429), body=None)

        translator._client.chat.completions.parse = always_fail

        unit, _ = make_unit("Hello")
        with pytest.raises(openai.RateLimitError):
            translator.translate([unit], "en", "fr")

    def test_raises_when_the_model_refuses_to_translate(self, translator, make_unit):
        translator._client.chat.completions.parse = lambda **kwargs: _response(refusal="unsafe content")

        unit, _ = make_unit("Hello")
        with pytest.raises(RuntimeError, match="refused"):
            translator.translate([unit], "en", "fr")

    def test_raises_when_the_response_has_no_parsed_translation(self, translator, make_unit):
        translator._client.chat.completions.parse = lambda **kwargs: _response(translation=None)

        unit, _ = make_unit("Hello")
        with pytest.raises(ValueError, match="no parsable translation"):
            translator.translate([unit], "en", "fr")
