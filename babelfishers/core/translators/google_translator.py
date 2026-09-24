import logging
import time

from google import genai
from google.genai import errors, types

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


@register(Engine.Google)
class GoogleTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.Google)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: genai.Client = genai.Client(api_key=get_env("BF_GOOGLE_API_KEY"))
        self._model: str = get_env("BF_GOOGLE_MODEL_ID")

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
                    response = self._client.models.generate_content(
                        model=self._model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                            response_schema=ModelTranslationResponse,
                            thinking_config=types.ThinkingConfig(thinking_budget=0),
                        ),
                    )
                    break
                except errors.ClientError as e:
                    if e.code in (401, 403):
                        self._logger.error(ConsoleFormatter.error("Google authorization failed — check API key"))
                        raise
                    if e.code != 429 or rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error(f"Google API error for unit: {e}"))
                        raise
                    headers = getattr(e.response, "headers", None)
                    retry_after = headers.get("retry-after") if headers else None
                    delay = (
                        float(retry_after)
                        if retry_after
                        else self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    )
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"Google rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except errors.ServerError as e:
                    self._logger.error(ConsoleFormatter.error(f"Google server error for unit: {e}"))
                    raise

            parsed = response.parsed
            if not isinstance(parsed, ModelTranslationResponse):
                self._logger.error(ConsoleFormatter.error("Google returned no parsable translation for unit"))
                raise ValueError("Google returned no parsable translation for unit")

            translated_text = parsed.translation.strip()
            unit.translated_text = translated_text

        return data
