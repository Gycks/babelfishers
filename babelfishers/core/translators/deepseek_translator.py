import logging
import time

import openai
from pydantic import ValidationError

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


_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_JSON_RESPONSE_INSTRUCTION = (
    f"\n\n## JSON response\nRespond with a single JSON object shaped as {ModelTranslationResponse.model_json_schema()} "
    "and nothing else."
)


@register(Engine.DeepSeek)
class DeepSeekTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.DeepSeek)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: openai.OpenAI = openai.OpenAI(api_key=get_env("BF_DEEPSEEK_API_KEY"), base_url=_DEEPSEEK_BASE_URL)
        self._model: str = get_env("BF_DEEPSEEK_MODEL_ID")

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        ignore_tag_shapes = TokenStrategyFactory.get_strategy_for(self._engine).ignore_tag_shapes
        system_prompt = (
            build_system_prompt(get_culture_name(source), get_culture_name(target), ignore_tag_shapes)
            + _JSON_RESPONSE_INSTRUCTION
        )

        for unit in data:
            if unit.skip_translation:
                continue

            user_prompt = build_user_prompt(unit.source_text, unit.context_hint)

            rate_limit_attempt = 0
            while True:
                try:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format={"type": "json_object"},
                    )
                    break
                except openai.AuthenticationError:
                    self._logger.error(ConsoleFormatter.error("DeepSeek authorization failed — check API key"))
                    raise
                except openai.PermissionDeniedError:
                    self._logger.error(ConsoleFormatter.error("DeepSeek API key lacks required permissions"))
                    raise
                except openai.RateLimitError as e:
                    if rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error("DeepSeek rate limit exceeded"))
                        raise
                    retry_after = e.response.headers.get("retry-after") if e.response is not None else None
                    delay = (
                        float(retry_after)
                        if retry_after
                        else self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    )
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"DeepSeek rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except openai.APIStatusError as e:
                    self._logger.error(ConsoleFormatter.error(f"DeepSeek API error for unit: {e}"))
                    raise
                except openai.APIConnectionError as e:
                    self._logger.error(ConsoleFormatter.error(f"DeepSeek connection error for unit: {e}"))
                    raise

            content = response.choices[0].message.content
            if not content:
                self._logger.error(ConsoleFormatter.error("DeepSeek returned an empty response for unit"))
                raise ValueError("DeepSeek returned an empty response for unit")

            try:
                parsed = ModelTranslationResponse.model_validate_json(content)
            except ValidationError as e:
                self._logger.error(ConsoleFormatter.error(f"DeepSeek returned malformed JSON for unit: {e}"))
                raise

            translated_text = parsed.translation.strip()
            unit.translated_text = translated_text

        return data
