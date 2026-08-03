import glob
import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.models.engine import Engine
from babelfishers.utils.console_formater import ConsoleFormatter


_PLACEHOLDER: str = "[source]"
_WILDCARD_TOKEN = re.compile(r"(\*\*/|\*\*|\*|\?)")
_logger: logging.Logger = logging.getLogger(__file__)


def _capturing_regex(glob_pattern: str) -> re.Pattern[str]:
    """Build a regex that captures exactly what each wildcard in a glob
    pattern matched, so that captured text can be substituted into a
    different (still-templated) version of the same pattern."""
    parts = _WILDCARD_TOKEN.split(glob_pattern)
    regex_parts = []
    for part in parts:
        if part in ("*", "?"):
            regex_parts.append("(.*)" if part == "*" else "(.)")
        elif part in ("**", "**/"):
            regex_parts.append("(.*)")
        else:
            regex_parts.append(re.escape(part))
    return re.compile("^" + "".join(regex_parts) + "$")


def _build_destination_pattern(raw_pattern: str, resolved_pattern: str, matched_path: str) -> str:
    """
    raw_pattern:      pattern with [source] still present, e.g. "locales/[source]/*.json"
    resolved_pattern: same pattern with [source] replaced by the real source locale
    matched_path:     a real file path that glob matched against resolved_pattern

    Returns raw_pattern with each wildcard replaced by what it actually
    matched on disk, while leaving [source] untouched for later
    locale substitution in get_destination_path.
    """
    regex = _capturing_regex(resolved_pattern)
    match = regex.match(matched_path)
    if match is None:
        return raw_pattern

    captured_values = iter(match.groups())
    parts = _WILDCARD_TOKEN.split(raw_pattern)
    rebuilt = [next(captured_values) if part in ("*", "?", "**", "**/") else part for part in parts]
    return "".join(rebuilt)


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
            return TranslationResourceType(name.lower().strip())
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
    engine: Engine | None
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

        if len(data) == 0:
            return []

        if len(data) != 1:
            raise ValueError(f"Resource {key} is malformed. Expected a single key, got: {list(data.keys())}")

        results = []

        for key_tag, paths in data.items():
            if key_tag != "paths":
                raise ValueError(f"Resource {resource_type} is malformed. Expected key: 'path', got: '{key_tag}'.")

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

                path_pattern = entry.get("path")
                if path_pattern is None:
                    raise ValueError(f"Resource {resource_type} is malformed. Missing key: 'path'.")

                resolved_pattern = path_pattern.replace(_PLACEHOLDER, locale)
                excluded_patterns = entry.get("exclude", [])
                if excluded_patterns is None:
                    excluded_patterns = []
                elif not isinstance(excluded_patterns, list):
                    raise TypeError(f"Resource {resource_type} is malformed. 'exclude' must be a list.")

                excluded = {
                    Path(p)
                    for exclude in excluded_patterns
                    if exclude is not None
                    for p in glob.glob(exclude.replace(_PLACEHOLDER, locale))
                }

                resource_paths = [
                    ResourcePath(
                        path=path,
                        pattern=_build_destination_pattern(path_pattern, resolved_pattern, str(path)),
                    )
                    for p in glob.glob(resolved_pattern, recursive=True)
                    if (path := Path(p)) not in excluded
                ]

                engine_string = entry.get("engine")
                engine: Engine | None = None

                if engine_string:
                    engine = Engine.validate(engine_string)
                    if engine is None:
                        msg = f"Invalid engine {engine_string} for [resource.{resource_type}]: {entry}."
                        _logger.warning(ConsoleFormatter.warning(msg))

                excluded_keys = entry.get("excluded_keys", [])
                if excluded_keys is None:
                    excluded_keys = []
                elif not isinstance(excluded_keys, list):
                    raise TypeError(f"Resource {resource_type} is malformed. 'excluded_keys' must be a list.")

                results.append(
                    cls(
                        resource_type=resource_type,
                        excluded_keys=[key for key in excluded_keys if key is not None],
                        engine=engine,
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
