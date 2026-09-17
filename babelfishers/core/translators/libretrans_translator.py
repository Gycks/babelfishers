import logging
import time
from urllib.error import HTTPError, URLError

from libretranslatepy import LibreTranslateAPI

from babelfishers.core.supported_cultures import get_culture_code_for_engine
from babelfishers.core.translators.registry import register
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_env


@register(Engine.LibreTranslate)
class LibreTranslateTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.LibreTranslate)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: LibreTranslateAPI = self.create_client()

    @staticmethod
    def create_client() -> LibreTranslateAPI:
        url: str | None = None
        try:
            url = get_env("BF_LIBRETRANSLATE_URL")
        except KeyError:
            pass

        api_key: str | None = None
        try:
            api_key = get_env("BF_LIBRETRANSLATE_API_KEY")
        except KeyError:
            pass

        return LibreTranslateAPI(url=url, api_key=api_key)

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        for unit in data:
            if unit.skip_translation:
                continue

            rate_limit_attempt = 0
            while True:
                try:
                    translated_text: str = self._client.translate(
                        unit.source_text,
                        source=get_culture_code_for_engine(source, self._engine),
                        target=get_culture_code_for_engine(target, self._engine),
                    )
                    break
                except HTTPError as e:
                    if e.code != 429 or rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error(f"LibreTranslate API error for unit: {e}"))
                        raise
                    delay = self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"LibreTranslate rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except URLError as e:
                    self._logger.error(ConsoleFormatter.error(f"LibreTranslate connection error for unit: {e}"))
                    raise

            unit.translated_text = translated_text
            unit.write_back(translated_text)

        return data
