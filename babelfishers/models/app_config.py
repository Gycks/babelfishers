import logging
import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.core.supported_cultures import SUPPORTED_CULTURES
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

    @classmethod
    def _parse_configuration(cls, config: dict[str, Any]) -> Self:
        locale_block = config.get("locale")
        if locale_block is None:
            raise ValueError("Invalid configuration file. Could not find a valid section named locale")

        source_locale = locale_block.get("source")
        if source_locale is None:
            raise ValueError("Invalid configuration file. Source locale not set.")

        if source_locale not in SUPPORTED_CULTURES.keys():
            raise ValueError("Invalid configuration file. Source locale {source_locale} is not supported.")

        target_locales = locale_block.get("targets")
        if target_locales is None or len(target_locales) == 0:
            raise ValueError("Invalid configuration file. Target locales not set.")

        if not set(target_locales).issubset(SUPPORTED_CULTURES):
            raise ValueError("Invalid configuration file. Targets locale is malformed.")

        engine_block = config.get("engine")
        if engine_block is None:
            raise ValueError("Invalid configuration file. Could not find a valid section named engine")

        engine_name = engine_block.get("provider")
        if engine_name is None:
            raise ValueError("Invalid configuration file. Engine provider not set.")

        engine = Engine.validate(engine_name)
        if engine is None:
            raise ValueError(f"Invalid configuration file. The Engine {engine_name} is not supported.")

        resources_block = config.get("resources")
        resources = TranslationResource.batch_load(source_locale, resources_block)

        translation_block = config.get("translation")
        glossary = None
        if translation_block is not None:
            glossary = Glossary.load(translation_block.get("glossary"))

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
            config_path (Path): Path to the underlying configuration file

        Returns:
            (AppConfig): The application configuration
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
