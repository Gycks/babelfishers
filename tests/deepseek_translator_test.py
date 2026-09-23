import httpx
import openai
import pytest
from pydantic import ValidationError

from babelfishers.core.translators.deepseek_translator import DeepSeekTranslator


def _http_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code, headers=headers or {}, request=httpx.Request("POST", "https://api.deepseek.com/x")
    )


def _response(content: str | None):
    message = type("Message", (), {"content": content})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice]})()


@pytest.fixture
def translator(monkeypatch) -> DeepSeekTranslator:
    monkeypatch.setenv("BF_DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("BF_DEEPSEEK_MODEL_ID", "deepseek-test")
    return DeepSeekTranslator()


class TestDeepSeekTranslatorTranslate:
    def test_writes_back_the_parsed_translation(self, translator, make_unit):
        translator._client.chat.completions.create = lambda **kwargs: _response('{"translation": "Bonjour"}')

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.chat.completions.create = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise openai.AuthenticationError("bad key", response=_http_response(401), body=None)

        translator._client.chat.completions.create = fail

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
            return _response('{"translation": "Bonjour"}')

        translator._client.chat.completions.create = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_on_empty_response_content(self, translator, make_unit):
        translator._client.chat.completions.create = lambda **kwargs: _response(None)

        unit, _ = make_unit("Hello")
        with pytest.raises(ValueError, match="empty response"):
            translator.translate([unit], "en", "fr")

    def test_raises_on_malformed_json_content(self, translator, make_unit):
        translator._client.chat.completions.create = lambda **kwargs: _response("not json")

        unit, _ = make_unit("Hello")
        with pytest.raises(ValidationError):
            translator.translate([unit], "en", "fr")
