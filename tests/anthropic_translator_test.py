import anthropic
import httpx
import pytest

from babelfishers.core.translators.anthropic_translator import AnthropicTranslator


def _http_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code, headers=headers or {}, request=httpx.Request("POST", "https://api.anthropic.com/x")
    )


def _response(translation: str | None = None, stop_reason: str = "end_turn"):
    parsed_output = type("Parsed", (), {"translation": translation})() if translation is not None else None
    return type("Response", (), {"stop_reason": stop_reason, "parsed_output": parsed_output})()


@pytest.fixture
def translator(monkeypatch) -> AnthropicTranslator:
    monkeypatch.setenv("BF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("BF_ANTHROPIC_MODEL_ID", "claude-test")
    return AnthropicTranslator()


class TestAnthropicTranslatorTranslate:
    def test_writes_back_the_parsed_translation(self, translator, make_unit):
        translator._client.messages.parse = lambda **kwargs: _response("Bonjour")

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.messages.parse = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise anthropic.AuthenticationError("bad key", response=_http_response(401), body=None)

        translator._client.messages.parse = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(anthropic.AuthenticationError):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise anthropic.RateLimitError("slow down", response=_http_response(429), body=None)
            return _response("Bonjour")

        translator._client.messages.parse = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_when_the_model_refuses_to_translate(self, translator, make_unit):
        translator._client.messages.parse = lambda **kwargs: _response(stop_reason="refusal")

        unit, _ = make_unit("Hello")
        with pytest.raises(RuntimeError, match="refused"):
            translator.translate([unit], "en", "fr")

    def test_raises_when_the_response_has_no_parsed_output(self, translator, make_unit):
        translator._client.messages.parse = lambda **kwargs: _response(translation=None)

        unit, _ = make_unit("Hello")
        with pytest.raises(ValueError, match="no parsable translation"):
            translator.translate([unit], "en", "fr")
