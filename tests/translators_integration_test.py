import os

import pytest

from babelfishers.core.translators.anthropic_translator import AnthropicTranslator
from babelfishers.core.translators.azure_translator import AzureTranslator
from babelfishers.core.translators.deepl_translator import DeeplTranslator
from babelfishers.core.translators.deepseek_translator import DeepSeekTranslator
from babelfishers.core.translators.google_translator import GoogleTranslator
from babelfishers.core.translators.googletrans_translator import GoogleTranslateTranslator
from babelfishers.core.translators.libretrans_translator import LibreTranslateTranslator
from babelfishers.core.translators.mistral_translator import MistralTranslator
from babelfishers.core.translators.openai_translator import OpenAITranslator
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import TranslationUnit


pytestmark = pytest.mark.integration


def _requires_env(*names: str):
    missing = [name for name in names if not os.getenv(name)]
    return pytest.mark.skipif(bool(missing), reason=f"missing env vars: {', '.join(missing)}")


def _translate_hello(translator_cls: type) -> str:
    written = {}
    unit = TranslationUnit(
        unit_type=TranslationResourceType.JSON,
        key="k1",
        source_text="Hello",
        write_back=lambda v: written.__setitem__("k1", v),
    )
    result = translator_cls().translate([unit], "en", "fr")

    assert result[0].translated_text
    assert written["k1"] == result[0].translated_text
    return result[0].translated_text


class TestRealTranslatorSmoke:
    @_requires_env("BF_OPENAI_API_KEY", "BF_OPENAI_MODEL_ID")
    def test_openai_translates_a_short_string(self):
        _translate_hello(OpenAITranslator)

    @_requires_env("BF_ANTHROPIC_API_KEY", "BF_ANTHROPIC_MODEL_ID")
    def test_anthropic_translates_a_short_string(self):
        _translate_hello(AnthropicTranslator)

    @_requires_env("BF_MISTRAL_API_KEY", "BF_MISTRAL_MODEL_ID")
    def test_mistral_translates_a_short_string(self):
        _translate_hello(MistralTranslator)

    @_requires_env("BF_DEEPSEEK_API_KEY", "BF_DEEPSEEK_MODEL_ID")
    def test_deepseek_translates_a_short_string(self):
        _translate_hello(DeepSeekTranslator)

    @_requires_env("BF_GOOGLE_API_KEY", "BF_GOOGLE_MODEL_ID")
    def test_google_gemini_translates_a_short_string(self):
        _translate_hello(GoogleTranslator)

    @_requires_env("BF_DEEPL_API_KEY")
    def test_deepl_translates_a_short_string(self):
        _translate_hello(DeeplTranslator)

    @_requires_env("BF_AZURE_API_KEY", "BF_AZURE_REGION")
    def test_azure_translates_a_short_string(self):
        _translate_hello(AzureTranslator)

    @_requires_env("BF_GOOGLE_PROJECT_ID")
    def test_google_cloud_translate_translates_a_short_string(self):
        _translate_hello(GoogleTranslateTranslator)

    @_requires_env("BF_LIBRETRANSLATE_URL")
    def test_libretranslate_translates_a_short_string(self):
        _translate_hello(LibreTranslateTranslator)
