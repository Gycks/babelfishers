import logging
import time

from mistralai.client import Mistral
from mistralai.client.errors import MistralError, NoResponseError

from babelfishers.core.supported_cultures import get_culture_name
from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.translators.llm_translator_toolkit import (
    ModelTranslationResponse,
    build_system_prompt,
    build_user_prompt,
)
from babelfishers.core.translators.registry import register
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_env


@register(Engine.Mistral)
class MistralTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.Mistral)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: Mistral = Mistral(api_key=get_env("BF_MISTRAL_API_KEY"))
        self._model: str = get_env("BF_MISTRAL_MODEL_ID")

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        ignore_tag_shapes = TokenStrategyFactory.get_strategy_for(self._engine).ignore_tag_shapes
        system_prompt = build_system_prompt(get_culture_name(source), get_culture_name(target), ignore_tag_shapes)

        for unit in data:
            if unit.skip_translation:
                continue

            user_prompt = build_user_prompt(unit.source_text, unit.context_hint)

            rate_limit_attempt = 0
            while True:
                try:
                    response = self._client.chat.parse(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format=ModelTranslationResponse,
                    )
                    break
                except NoResponseError as e:
                    self._logger.error(ConsoleFormatter.error(f"Mistral connection error for unit: {e}"))
                    raise
                except MistralError as e:
                    if e.status_code in (401, 403):
                        self._logger.error(ConsoleFormatter.error("Mistral authorization failed — check API key"))
                        raise
                    if e.status_code != 429 or rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error(f"Mistral API error for unit: {e}"))
                        raise
                    retry_after = e.headers.get("retry-after")
                    delay = (
                        float(retry_after)
                        if retry_after
                        else self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    )
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"Mistral rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1

            choice = response.choices[0] if response.choices else None
            parsed = choice.message.parsed if choice is not None and choice.message is not None else None
            if parsed is None:
                self._logger.error(ConsoleFormatter.error("Mistral returned no parsable translation for unit"))
                raise ValueError("Mistral returned no parsable translation for unit")

            translated_text = parsed.translation.strip()
            unit.translated_text = translated_text

        return data
