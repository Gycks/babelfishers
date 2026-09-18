from types import SimpleNamespace

import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError

from babelfishers.core.translators.azure_translator import AzureTranslator


def _http_error(status_code: int, headers: dict | None = None) -> HttpResponseError:
    response = SimpleNamespace(status_code=status_code, reason="error", headers=headers or {}, text=lambda: "")
    return HttpResponseError(response=response)


def _result(text: str):
    translation = type("Translation", (), {"text": text})()
    return [type("Item", (), {"translations": [translation]})()]


@pytest.fixture
def translator(monkeypatch) -> AzureTranslator:
    monkeypatch.setenv("BF_AZURE_REGION", "eastus")
    monkeypatch.setenv("BF_AZURE_API_KEY", "test-key")
    return AzureTranslator()


class TestAzureTranslatorTranslate:
    def test_writes_back_the_translated_text(self, translator, make_unit):
        translator._client.translate = lambda **kwargs: _result("Bonjour")

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.translate = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise ClientAuthenticationError(message="bad key")

        translator._client.translate = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(ClientAuthenticationError):
            translator.translate([unit], "en", "fr")

    def test_raises_immediately_on_connection_error(self, translator, make_unit):
        def fail(**kwargs):
            raise ServiceRequestError("connection failed")

        translator._client.translate = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(ServiceRequestError):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise _http_error(429)
            return _result("Bonjour")

        translator._client.translate = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_immediately_on_non_rate_limit_api_error(self, translator, make_unit):
        def fail(**kwargs):
            raise _http_error(500)

        translator._client.translate = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(HttpResponseError):
            translator.translate([unit], "en", "fr")
