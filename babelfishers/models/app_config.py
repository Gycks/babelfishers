import logging
import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.core.supported_cultures import (
    get_distinct_targets,
    get_unsupported_cultures,
    resolve_culture_code,
)
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary
from babelfishers.models.translation_resource import TranslationResource
from babelfishers.utils.console_formater import ConsoleFormatter


logger: logging.Logger = logging.getLogger(__name__)


class AppConfig(BaseModel):
    source_locale: str
    target_locales: list[str]
    resources: list[TranslationResource]
    translation_engine: Engine
    glossary: Glossary | None

    @staticmethod
    def _parse_target_locales(source_locale: str, target_locales: Any) -> list[str]:
        """Resolve the target codes, whatever their case, dropping repeats and the source locale.

        A plain code and its default variant, such as `pt` and `pt-PT`, are the same locale, so both
        can't be targets, and a target that is the source locale under another code is dropped too.
        Fails when no target is left.
        """
        if not isinstance(target_locales, list):
            raise ValueError("Invalid configuration file. Target locales is malformed. Use a list of locale codes.")

        unknown = [
            str(code) for code in target_locales if not isinstance(code, str) or resolve_culture_code(code) is None
        ]
        if unknown:
            raise ValueError(
                f"Invalid configuration file. Target locales {', '.join(unknown)} are not supported. "
                "Run `babelfishers locales` to list the supported ones."
            )

        resolved = [resolve_culture_code(code) or code for code in target_locales]
        try:
            distinct = get_distinct_targets(source_locale, resolved)
        except ValueError as exc:
            raise ValueError(f"Invalid configuration file. {exc}") from exc

        if not distinct:
            raise ValueError(
                "Invalid configuration file. Target locales not set. "
                f"Every target is the source locale {source_locale}."
            )

        return distinct

    @staticmethod
    def _check_engine_locales(engine: Engine, source_locale: str, target_locales: list[str], where: str = "") -> None:
        unsupported = get_unsupported_cultures(engine, source_locale, target_locales)
        if unsupported:
            raise ValueError(
                f"Invalid configuration file. The engine {engine.value}{where} does not support the locale(s) "
                f"{', '.join(unsupported)}. Pick another engine, or see which engine supports which locale at "
                "https://gycks.github.io/babelfishers/reference/locales/"
            )

    @classmethod
    def _parse_configuration(cls, config: dict[str, Any]) -> Self:
        locale_block = config.get("locale")
        if locale_block is None:
            raise ValueError("Invalid configuration file. Could not find a valid section named locale")

        source_locale = locale_block.get("source")
        if source_locale is None:
            raise ValueError("Invalid configuration file. Source locale not set.")

        resolved_source = resolve_culture_code(source_locale) if isinstance(source_locale, str) else None
        if resolved_source is None:
            raise ValueError(f"Invalid configuration file. Source locale {source_locale} is not supported.")
        source_locale = resolved_source

        target_locales = locale_block.get("targets")
        if target_locales is None or len(target_locales) == 0:
            raise ValueError("Invalid configuration file. Target locales not set.")

        target_locales = cls._parse_target_locales(source_locale, target_locales)

        engine_block = config.get("engine")
        if engine_block is None:
            raise ValueError("Invalid configuration file. Could not find a valid section named engine")

        engine_name = engine_block.get("provider")
        if engine_name is None:
            raise ValueError("Invalid configuration file. Engine provider not set.")

        engine = Engine.validate(engine_name)
        if engine is None:
            raise ValueError(f"Invalid configuration file. The Engine {engine_name} is not supported.")

        cls._check_engine_locales(engine, source_locale, target_locales)

        resources_block = config.get("resources")
        resources = TranslationResource.batch_load(source_locale, resources_block)
        for resource in resources:
            if resource.engine is not None:
                where = f" (set on a [resources.{resource.resource_type}] path)"
                cls._check_engine_locales(resource.engine, source_locale, target_locales, where)

        translation_block = config.get("translation")
        glossary = None
        if translation_block is not None:
            glossary = Glossary.load(translation_block.get("glossary"))

        logger.info(ConsoleFormatter.info("Successfully loaded app configuration"))

        return cls(
            source_locale=source_locale,
            target_locales=target_locales,
            translation_engine=engine,
            resources=resources,
            glossary=glossary,
        )

    @classmethod
    def load(cls, config_path: Path) -> Self:
        """
        Loads the application configuration

        Args:
            config_path: Path to the underlying configuration file

        Returns:
            The application configuration
        """

        logger.info(ConsoleFormatter.info("Loading app configuration"))

        if not config_path.is_file():
            raise FileNotFoundError(f"Could not find any configuration file at {config_path}")

        if config_path.suffix.strip().lower() != ".toml":
            raise ValueError("The configuration file must be a valid TOML file")

        raw_config: dict[str, Any]
        with config_path.open("rb") as reader:
            raw_config = tomllib.load(reader)

        return cls._parse_configuration(raw_config)
