import logging
import time

import openai

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


@register(Engine.OpenAI)
class OpenAITranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.OpenAI)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: openai.OpenAI = openai.OpenAI(api_key=get_env("BF_OPENAI_API_KEY"))
        self._model: str = get_env("BF_OPENAI_MODEL_ID")

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
                    response = self._client.chat.completions.parse(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format=ModelTranslationResponse,
                    )
                    break
                except openai.AuthenticationError:
                    self._logger.error(ConsoleFormatter.error("OpenAI authorization failed — check API key"))
                    raise
                except openai.PermissionDeniedError:
                    self._logger.error(ConsoleFormatter.error("OpenAI API key lacks required permissions"))
                    raise
                except openai.RateLimitError as e:
                    if rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error("OpenAI rate limit exceeded"))
                        raise
                    retry_after = e.response.headers.get("retry-after") if e.response is not None else None
                    delay = (
                        float(retry_after)
                        if retry_after
                        else self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    )
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"OpenAI rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except openai.APIStatusError as e:
                    self._logger.error(ConsoleFormatter.error(f"OpenAI API error for unit: {e}"))
                    raise
                except openai.APIConnectionError as e:
                    self._logger.error(ConsoleFormatter.error(f"OpenAI connection error for unit: {e}"))
                    raise

            message = response.choices[0].message
            if message.refusal:
                self._logger.error(ConsoleFormatter.error("OpenAI refused to translate unit"))
                raise RuntimeError("OpenAI refused to translate unit")

            if message.parsed is None:
                self._logger.error(ConsoleFormatter.error("OpenAI returned no parsable translation for unit"))
                raise ValueError("OpenAI returned no parsable translation for unit")

            translated_text = message.parsed.translation.strip()
            unit.translated_text = translated_text

        return data
