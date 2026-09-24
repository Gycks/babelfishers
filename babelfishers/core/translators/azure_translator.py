import logging
import time

from azure.ai.translation.text import TextTranslationClient
from azure.ai.translation.text.models import TextType, TranslatedTextItem, TranslateInputItem, TranslationTarget
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)

from babelfishers.core.supported_cultures import get_culture_code_for_engine
from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.translators.registry import register
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


@register(Engine.Azure)
class AzureTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.Azure)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: TextTranslationClient = self.create_client()

    @staticmethod
    def create_client() -> TextTranslationClient:
        from azure.core.credentials import AzureKeyCredential

        from babelfishers.utils.utils import get_env

        endpoint: str | None = None
        try:
            endpoint = get_env("BF_AZURE_ENDPOINT")
        except KeyError:
            pass

        region = get_env("BF_AZURE_REGION")
        credential = AzureKeyCredential(get_env("BF_AZURE_API_KEY"))

        if endpoint:
            return TextTranslationClient(
                endpoint=endpoint,
                credential=credential,
                region=region,
            )
        else:
            return TextTranslationClient(
                credential=credential,
                region=region,
            )

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        ignore_tags = TokenStrategyFactory.get_strategy_for(self._engine).ignore_tag_names
        text_type = TextType.HTML if len(ignore_tags) else TextType.PLAIN

        for unit in data:
            if unit.skip_translation:
                continue

            rate_limit_attempt = 0
            while True:
                try:
                    result: list[TranslatedTextItem] = self._client.translate(
                        body=[
                            TranslateInputItem(
                                text=unit.source_text,
                                language=get_culture_code_for_engine(source, self._engine),
                                text_type=text_type,
                                targets=[TranslationTarget(language=get_culture_code_for_engine(target, self._engine))],
                            )
                        ],
                    )
                    break
                except ClientAuthenticationError:
                    self._logger.error(ConsoleFormatter.error("Azure authorization failed — check API key"))
                    raise
                except (ServiceRequestError, ServiceResponseError) as e:
                    self._logger.error(ConsoleFormatter.error(f"Azure Translator network error for unit: {e}"))
                    raise
                except HttpResponseError as e:
                    if e.status_code != 429 or rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error(f"Azure Translator API error for unit: {e}"))
                        raise

                    headers = getattr(e.response, "headers", None) if e.response else None
                    retry_after = headers.get("Retry-After") if headers else None
                    delay = (
                        float(retry_after)
                        if retry_after
                        else self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    )
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"Azure Translator rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1

            translated_text = result[0].translations[0].text
            unit.translated_text = translated_text

        return data
