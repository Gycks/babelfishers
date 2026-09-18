import httpx
import pytest
from mistralai.client.errors import MistralError, NoResponseError

from babelfishers.core.translators.mistral_translator import MistralTranslator


def _http_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, headers=headers or {}, request=httpx.Request("POST", "https://api.mistral.ai/x"))


def _response(translation: str | None):
    parsed = type("Parsed", (), {"translation": translation})() if translation is not None else None
    message = type("Message", (), {"parsed": parsed})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice]})()


@pytest.fixture
def translator(monkeypatch) -> MistralTranslator:
    monkeypatch.setenv("BF_MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("BF_MISTRAL_MODEL_ID", "mistral-test")
    return MistralTranslator()


class TestMistralTranslatorTranslate:
    def test_writes_back_the_parsed_translation(self, translator, make_unit):
        translator._client.chat.parse = lambda **kwargs: _response("Bonjour")

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.chat.parse = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise MistralError("bad key", raw_response=_http_response(401))

        translator._client.chat.parse = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(MistralError):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise MistralError("slow down", raw_response=_http_response(429))
            return _response("Bonjour")

        translator._client.chat.parse = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_on_connection_error(self, translator, make_unit):
        def fail(**kwargs):
            raise NoResponseError("no response")

        translator._client.chat.parse = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(NoResponseError):
            translator.translate([unit], "en", "fr")

    def test_raises_when_the_response_has_no_parsed_translation(self, translator, make_unit):
        translator._client.chat.parse = lambda **kwargs: _response(translation=None)

        unit, _ = make_unit("Hello")
        with pytest.raises(ValueError, match="no parsable translation"):
            translator.translate([unit], "en", "fr")
