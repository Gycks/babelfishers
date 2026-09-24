import logging
import time

from deepl import (
    AuthorizationException,
    DeepLClient,
    DeepLException,
    QuotaExceededException,
    TextResult,
    TooManyRequestsException,
)

from babelfishers.core.supported_cultures import get_culture_code_for_engine
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
        self._translator: DeepLClient = DeepLClient(get_env("BF_DEEPL_API_KEY"))

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        ignore_tags = TokenStrategyFactory.get_strategy_for(self._engine).ignore_tag_names

        for unit in data:
            if unit.skip_translation:
                continue

            rate_limit_attempt = 0
            while True:
                try:
                    result: TextResult | list[TextResult] = self._translator.translate_text(
                        unit.source_text,
                        source_lang=get_culture_code_for_engine(source, self._engine),
                        target_lang=get_culture_code_for_engine(target, self._engine),
                        context=unit.context_hint,
                        preserve_formatting=True,
                        tag_handling="xml" if ignore_tags else None,
                        ignore_tags=ignore_tags or None,
                    )
                    break
                except QuotaExceededException:
                    self._logger.error(ConsoleFormatter.error("DeepL quota exceeded, skipping unit"))
                    raise
                except TooManyRequestsException:
                    if rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error("DeepL rate limit exceeded after internal retries"))
                        raise
                    delay = self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"DeepL rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except AuthorizationException:
                    self._logger.error(ConsoleFormatter.error("DeepL authorization failed — check API key"))
                    raise
                except DeepLException as e:
                    self._logger.error(ConsoleFormatter.error(f"DeepL API error for unit: {e}"))
                    raise

            if isinstance(result, list):
                raise TypeError(ConsoleFormatter.error("Invalid DeepL response format type"))

            unit.translated_text = result.text

        return data
