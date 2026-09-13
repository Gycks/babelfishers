import logging

from deepl import (
    AuthorizationException,
    DeepLClient,
    DeepLException,
    QuotaExceededException,
    TextResult,
    TooManyRequestsException,
)

from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.translators.registry import register
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_env


@register(Engine.DeepL)
class DeeplTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.DeepL)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._translator: DeepLClient = DeepLClient(get_env("DEEPL_API_KEY"))

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        ignore_tags = TokenStrategyFactory.get_strategy_for(self._engine).ignore_tag_names

        for unit in data:
            if unit.skip_translation:
                continue

            try:
                result: TextResult | list[TextResult] = self._translator.translate_text(
                    unit.source_text,
                    source_lang=source,
                    target_lang=target,
                    context=unit.context_hint,
                    preserve_formatting=True,
                    tag_handling="xml" if ignore_tags else None,
                    ignore_tags=ignore_tags or None,
                )
            except QuotaExceededException:
                self._logger.error(ConsoleFormatter.error("DeepL quota exceeded, skipping unit"))
                raise
            except TooManyRequestsException:
                self._logger.error(ConsoleFormatter.error("DeepL rate limit exceeded after internal retries"))
                raise
            except AuthorizationException:
                self._logger.error(ConsoleFormatter.error("DeepL authorization failed — check API key"))
                raise
            except DeepLException as e:
                self._logger.error(ConsoleFormatter.error(f"DeepL API error for unit: {e}"))
                raise

            if isinstance(result, list):
                raise TypeError(ConsoleFormatter.error("Invalid DeepL response format type"))

            unit.translated_text = result.text
            unit.write_back(result.text)

        return data
