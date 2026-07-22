import glob
import logging
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.models.engine import Engine
from babelfishers.utils.console_formater import ConsoleFormatter


_PLACEHOLDER: str = "[source]"
_logger: logging.Logger = logging.getLogger(__file__)


class TranslationResourceType(StrEnum):
    HTML = "html"
    JSON = "json"
    YAML = "yaml"
    JAVA_PROPERTIES = "properties"
    ANDROID_STRINGS = "android"
    GETTEXT = "po"
    APPLE_STRINGS = "apple"
    FLUTTER_ARB = "arb"
    XLIFF = "xliff"
    DOTNET_RESX = "resx"

    @classmethod
    def validate(cls, name: str) -> Self | None:
        try:
            return TranslationResourceType(name)
        except ValueError:
            return None


class ResourcePath(BaseModel):
    path: Path
    pattern: str

    def get_destination_path(self, locale: str) -> Path:
        if _PLACEHOLDER in self.pattern:
            return Path(self.pattern.replace(_PLACEHOLDER, locale))

        return self.path.with_name(f"{self.path.stem}_{locale}{self.path.suffix}")


class TranslationResource(BaseModel):
    resource_type: TranslationResourceType
    excluded_keys: list[str]
    engines: Engine | None
    paths: list[ResourcePath]

    @classmethod
    def load(
        cls,
        locale: str,
        key: str,
        data: dict[str, Any],
    ) -> list[Self]:

        resource_type = TranslationResourceType.validate(key)
        if resource_type is None:
            raise ValueError(f"Invalid resource type {key}.")

        results = []

        for paths in data.values():
            for entry in paths:
                if isinstance(entry, str):
                    entry = {
                        "path": entry,
                        "exclude": [],
                        "engine": None,
                        "excluded_keys": [],
                    }
                elif not isinstance(entry, dict):
                    raise TypeError(f"Resource {resource_type} is malformed.")

                path_pattern = entry["path"]
                resolved_pattern = path_pattern.replace(_PLACEHOLDER, locale)

                excluded = {
                    Path(p)
                    for exclude in entry.get("exclude", [])
                    for p in glob.glob(exclude.replace(_PLACEHOLDER, locale))
                }

                resource_paths = [
                    ResourcePath(
                        path=path,
                        pattern=path_pattern.replace("*", path.name),
                    )
                    for p in glob.glob(resolved_pattern, recursive=True)
                    if (path := Path(p)) not in excluded
                ]

                engine_string = entry.get("engine")
                engine: Engine | None = None

                if engine_string:
                    engine = Engine.validate(engine_string)
                    msg = f"Invalid engine {engine_string} for [resource.{resource_type}]: {entry}."
                    _logger.warning(ConsoleFormatter.warning(msg))

                results.append(
                    cls(
                        resource_type=resource_type,
                        excluded_keys=entry.get("excluded_keys", []),
                        engines=engine,
                        paths=resource_paths,
                    )
                )

        return results

    @classmethod
    def batch_load(cls, locale: str, data: dict[str, Any] | None) -> list[Self]:
        if data is None:
            return []

        resources = []
        resource_key: str
        content: dict[str, Any]

        for resource_key, content in data.items():
            resources += cls.load(locale, resource_key, content)

        return resources
