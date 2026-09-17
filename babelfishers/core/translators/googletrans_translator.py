import logging
import time

from google.api_core.exceptions import GoogleAPICallError, TooManyRequests, Unauthorized
from google.cloud import translate

from babelfishers.core.supported_cultures import get_culture_code_for_engine
from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.translators.registry import register
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_env


@register(Engine.GoogleTranslate)
class GoogleTranslateTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.GoogleTranslate)
        self._logger: logging.Logger = logging.getLogger(__name__)

        self._project_id: str = get_env("BF_GOOGLE_PROJECT_ID")
        try:
            self._location: str = get_env("BF_GOOGLE_LOCATION")
        except KeyError:
            self._location = "global"

        self._client: translate.TranslationServiceClient = self.create_client()

    @staticmethod
    def create_client() -> translate.TranslationServiceClient:
        credentials = None
        try:
            key_path = get_env("BF_GOOGLE_APPLICATION_CREDENTIALS")
        except KeyError:
            key_path = None

        if key_path:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(key_path)  # type: ignore[no-untyped-call]

        return translate.TranslationServiceClient(credentials=credentials)

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        ignore_tags = TokenStrategyFactory.get_strategy_for(self._engine).ignore_tag_names
        mime_type = "text/html" if len(ignore_tags) else "text/plain"
        parent = f"projects/{self._project_id}/locations/{self._location}"

        for unit in data:
            if unit.skip_translation:
                continue

            rate_limit_attempt = 0
            while True:
                try:
                    response: translate.TranslateTextResponse = self._client.translate_text(
                        contents=[unit.source_text],
                        target_language_code=get_culture_code_for_engine(target, self._engine),
                        source_language_code=get_culture_code_for_engine(source, self._engine),
                        mime_type=mime_type,
                        parent=parent,
                    )
                    break
                except Unauthorized:
                    self._logger.error(
                        ConsoleFormatter.error("Google Translate authorization failed — check credentials")
                    )
                    raise
                except TooManyRequests:
                    if rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error("Google Translate rate limit exceeded"))
                        raise
                    delay = self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"Google Translate rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except GoogleAPICallError as e:
                    self._logger.error(ConsoleFormatter.error(f"Google Translate API error for unit: {e}"))
                    raise

            translated_text = response.translations[0].translated_text
            unit.translated_text = translated_text
            unit.write_back(translated_text)

        return data
