import logging
import time

import anthropic

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


@register(Engine.Anthropic)
class AnthropicTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.Anthropic)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._client: anthropic.Anthropic = anthropic.Anthropic(api_key=get_env("BF_ANTHROPIC_API_KEY"))
        self._model: str = get_env("BF_ANTHROPIC_MODEL_ID")

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
                    response = self._client.messages.parse(
                        model=self._model,
                        max_tokens=4096,
                        thinking={"type": "disabled"},
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                        output_format=ModelTranslationResponse,
                    )
                    break
                except anthropic.AuthenticationError:
                    self._logger.error(ConsoleFormatter.error("Anthropic authorization failed — check API key"))
                    raise
                except anthropic.PermissionDeniedError:
                    self._logger.error(ConsoleFormatter.error("Anthropic API key lacks required permissions"))
                    raise
                except anthropic.RateLimitError as e:
                    if rate_limit_attempt >= self._MAX_RATE_LIMIT_RETRIES:
                        self._logger.error(ConsoleFormatter.error("Anthropic rate limit exceeded"))
                        raise
                    retry_after = e.response.headers.get("retry-after") if e.response is not None else None
                    delay = (
                        float(retry_after)
                        if retry_after
                        else self._RATE_LIMIT_BASE_DELAY_SECONDS * (2**rate_limit_attempt)
                    )
                    self._logger.warning(
                        ConsoleFormatter.warning(
                            f"Anthropic rate limited, retrying unit in {delay:.1f}s "
                            f"(attempt {rate_limit_attempt + 1}/{self._MAX_RATE_LIMIT_RETRIES})"
                        )
                    )
                    time.sleep(delay)
                    rate_limit_attempt += 1
                except anthropic.APIStatusError as e:
                    self._logger.error(ConsoleFormatter.error(f"Anthropic API error for unit: {e}"))
                    raise
                except anthropic.APIConnectionError as e:
                    self._logger.error(ConsoleFormatter.error(f"Anthropic connection error for unit: {e}"))
                    raise

            if response.stop_reason == "refusal":
                self._logger.error(ConsoleFormatter.error("Anthropic refused to translate unit"))
                raise RuntimeError("Anthropic refused to translate unit")

            if response.parsed_output is None:
                self._logger.error(ConsoleFormatter.error("Anthropic returned no parsable translation for unit"))
                raise ValueError("Anthropic returned no parsable translation for unit")

            translated_text = response.parsed_output.translation.strip()
            unit.translated_text = translated_text

        return data
