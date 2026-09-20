from urllib.error import HTTPError, URLError

import pytest

from babelfishers.core.translators.libretrans_translator import LibreTranslateTranslator


def _http_error(code: int) -> HTTPError:
    return HTTPError("http://libretranslate.test", code, "error", {}, None)


@pytest.fixture
def translator(monkeypatch) -> LibreTranslateTranslator:
    monkeypatch.setenv("BF_LIBRETRANSLATE_URL", "http://libretranslate.test")
    return LibreTranslateTranslator()


class TestLibreTranslateTranslatorConfiguration:
    def test_requires_the_server_url(self, monkeypatch):
        monkeypatch.delenv("BF_LIBRETRANSLATE_URL", raising=False)

        with pytest.raises(KeyError, match="BF_LIBRETRANSLATE_URL"):
            LibreTranslateTranslator()

    def test_api_key_is_optional(self, monkeypatch):
        monkeypatch.setenv("BF_LIBRETRANSLATE_URL", "http://libretranslate.test")
        monkeypatch.delenv("BF_LIBRETRANSLATE_API_KEY", raising=False)

        assert LibreTranslateTranslator() is not None


class TestLibreTranslateTranslatorTranslate:
    def test_writes_back_the_translated_text(self, translator, make_unit):
        translator._client.translate = lambda *args, **kwargs: "Bonjour"

        unit, written = make_unit("Hello")
        result = translator.translate([unit], "en", "fr")

        assert result[0].translated_text == "Bonjour"
        assert written["k1"] == "Bonjour"

    def test_skips_units_marked_skip_translation(self, translator, make_unit):
        calls = []
        translator._client.translate = lambda *args, **kwargs: calls.append(args)

        unit, written = make_unit("Hello", skip_translation=True)
        translator.translate([unit], "en", "fr")

        assert calls == []
        assert written == {}

    def test_retries_then_succeeds_after_a_rate_limit_error(self, translator, make_unit, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise _http_error(429)
            return "Bonjour"

        translator._client.translate = flaky

        unit, written = make_unit("Hello")
        translator.translate([unit], "en", "fr")

        assert len(calls) == 2
        assert written["k1"] == "Bonjour"

    def test_raises_immediately_on_non_rate_limit_http_error(self, translator, make_unit):
        def fail(*args, **kwargs):
            raise _http_error(500)

        translator._client.translate = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(HTTPError):
            translator.translate([unit], "en", "fr")

    def test_raises_immediately_on_connection_error(self, translator, make_unit):
        def fail(*args, **kwargs):
            raise URLError("connection refused")

        translator._client.translate = fail

        unit, _ = make_unit("Hello")
        with pytest.raises(URLError):
            translator.translate([unit], "en", "fr")
