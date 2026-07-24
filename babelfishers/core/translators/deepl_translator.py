import logging

from deepl import (
    AuthorizationException,
    DeepLClient,
    DeepLException,
    QuotaExceededException,
    TextResult,
    TooManyRequestsException,
)

from babelfishers.core.translators.registry import register
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.utils import get_env


@register(Engine.DeepL)
class DeeplTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.DeepL)
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._translator: DeepLClient = DeepLClient(get_env("DEEPL_API_KEY"))

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        for unit in data:
            if unit.skip_translation:
                continue

            try:
                result: TextResult | list[TextResult] = self._translator.translate_text(
                    unit.source_text,
                    source_lang=source,
                    target_lang=target,
                    context=unit.context_hint,
                )
            except QuotaExceededException:
                self._logger.error(f"DeepL quota exceeded, skipping unit '{unit.key}'")
                raise
            except TooManyRequestsException:
                self._logger.error(f"DeepL rate limit exceeded after internal retries, unit '{unit.key}'")
                raise
            except AuthorizationException:
                self._logger.error("DeepL authorization failed — check API key")
                raise
            except DeepLException as e:
                self._logger.error(f"DeepL API error for unit '{unit.key}': {e}")
                raise

            if isinstance(result, list):
                raise TypeError("Invalid DeepL response format type")

            unit.translated_text = result.text
            unit.write_back(result.text)

        return data
