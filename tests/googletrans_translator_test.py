import pytest
from google.api_core.exceptions import GoogleAPICallError, TooManyRequests, Unauthorized

from babelfishers.core.translators.googletrans_translator import GoogleTranslateTranslator


def _response(text: str):
    translation = type("Translation", (), {"translated_text": text})()
    return type("Response", (), {"translations": [translation]})()


@pytest.fixture
def translator(monkeypatch) -> GoogleTranslateTranslator:
    monkeypatch.setenv("BF_GOOGLE_PROJECT_ID", "test-project")
    monkeypatch.setattr(GoogleTranslateTranslator, "create_client", staticmethod(lambda: type("FakeClient", (), {})()))
    return GoogleTranslateTranslator()


class TestGoogleTranslateTranslatorTranslate:
    def test_writes_back_the_translated_text(self, translator, make_unit):
        translator._client.translate_text = lambda **kwargs: _response("Bonjour")

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.translate_text = lambda **kwargs: calls.append(kwargs)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_raises_immediately_on_authentication_error(self, translator, make_unit):
        def fail(**kwargs):
            raise Unauthorized("bad credentials")

        translator._client.translate_text = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(Unauthorized):
            translator.translate([unit], "en", "fr")

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise TooManyRequests("slow down")
            return _response("Bonjour")

        translator._client.translate_text = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_immediately_on_other_api_errors(self, translator, make_unit):
        def fail(**kwargs):
            raise GoogleAPICallError("bad request")

        translator._client.translate_text = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(GoogleAPICallError):
            translator.translate([unit], "en", "fr")
