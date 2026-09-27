import glob
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field

from babelfishers.models.translation_resource import _PLACEHOLDER, TranslationResourceType


class ExtractType(StrEnum):
    PYTHON = "python"
    DJANGO = "django"
    DOTNET = "dotnet"
    I18NEXT = "i18next"
    ANGULAR = "angular"

    @classmethod
    def validate(cls, name: str) -> Self | None:
        try:
            return cls(name.lower().strip())
        except ValueError:
            return None

    @property
    def resource_type(self) -> TranslationResourceType:
        """The format of the file this extractor writes, which translate then reads."""
        return _RESOURCE_TYPES[self]

    @property
    def catalog(self) -> str:
        """The catalog pattern: where the framework reads the app's strings, relative to the app's root."""
        return _CATALOGS[self]


_RESOURCE_TYPES: dict[ExtractType, TranslationResourceType] = {
    ExtractType.PYTHON: TranslationResourceType.GETTEXT,
    ExtractType.DJANGO: TranslationResourceType.GETTEXT,
    ExtractType.DOTNET: TranslationResourceType.DOTNET_RESX,
    ExtractType.I18NEXT: TranslationResourceType.JSON,
    ExtractType.ANGULAR: TranslationResourceType.XLIFF,
}

_CATALOGS: dict[ExtractType, str] = {
    ExtractType.PYTHON: "locale/[source]/LC_MESSAGES/messages.po",
    ExtractType.DJANGO: "locale/[source]/LC_MESSAGES/django.po",
    ExtractType.DOTNET: "Resources",
    ExtractType.I18NEXT: "public/locales/[source]/translation.json",
    ExtractType.ANGULAR: "src/locale/messages.xlf",
}

_ALLOWED_KEYS = {"root", "exclude"}


class Extract(BaseModel):
    extract_type: ExtractType
    root: Path
    exclude: list[Path]

    @classmethod
    def load(cls, key: str, data: dict[str, Any]) -> list[Self]:
        extract_type = ExtractType.validate(key)
        if extract_type is None:
            raise ValueError(f"Invalid extract type {key}. Expected one of: {', '.join(ExtractType)}.")

        unknown = set(data) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(f"Extract {extract_type} is malformed. Unexpected keys: {sorted(unknown)}.")

        roots = data.get("root") or "."
        if isinstance(roots, str):
            roots = [roots]
        elif not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
            raise TypeError(f"Extract {extract_type} is malformed. 'root' must be a string or a list of strings.")

        excluded_patterns = data.get("exclude") or []
        if not isinstance(excluded_patterns, list):
            raise TypeError(f"Extract {extract_type} is malformed. 'exclude' must be a list.")

        results = []
        for root in roots:
            root_path = Path(root)
            if not root_path.is_dir():
                raise ValueError(f"Extract {extract_type} is malformed. Root '{root}' is not a folder.")
            excluded = {
                path
                for pattern in excluded_patterns
                if pattern is not None
                for p in glob.glob(str(root_path / pattern), recursive=True)
                if (path := Path(p)).exists()
            }
            results.append(cls(extract_type=extract_type, root=root_path, exclude=sorted(excluded)))

        return results

    @classmethod
    def batch_load(cls, data: dict[str, Any] | None) -> list[Self]:
        if data is None:
            return []

        return [extract for key, table in data.items() for extract in cls.load(key, table or {})]

    @property
    def catalog_pattern(self) -> str:
        """The catalog path with [source] still in it, relative to the folder of babelfishers.toml."""
        return (self.root.joinpath(self.extract_type.catalog)).as_posix()

    def catalog_path(self, locale: str) -> Path:
        """The catalog file for one locale. For the source locale, extract reads it (when it
        exists), merges and writes it back"""
        return Path(self.catalog_pattern.replace(_PLACEHOLDER, locale))

    def is_excluded(self, path: Path) -> bool:
        """True for an excluded file, or for anything inside an excluded folder."""
        return any(path == excluded or excluded in path.parents for excluded in self.exclude)


class CodeLocation(BaseModel):
    path: Path
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.path}, Line: {self.line}" if self.line else f"{self.path}, Line: unknown"


class ScannedString(BaseModel):
    """One translatable string found in the code."""

    catalog: str
    key: str
    text: str | None
    plural: str | None = None
    context: str | None = None
    comments: list[str] = Field(default_factory=list)
    location: CodeLocation


class SkippedCall(BaseModel):
    """A call whose text could not be read, because it is built at runtime."""

    location: CodeLocation
    code: str = Field(description="The call as written, for example _(status).")
    reason: str


class ScanResult(BaseModel):
    strings: list[ScannedString] = Field(default_factory=list)
    skipped: list[SkippedCall] = Field(default_factory=list)
