import hashlib
import logging
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import hash_file_contents


def excluded_keys_without_duplicates(
    excluded_keys: list[str], units: list[TranslationUnit], logger: logging.Logger
) -> set[str]:
    """
    A key can appear more than once in a file, for example a flat `"a.b"` next to a
    nested `{"a": {"b": ...}}`. Such a key doesn't point at one value, so each of its
    values is translated and an `excluded_keys` entry for it is ignored.

    Args:
        excluded_keys: The keys the configuration leaves untranslated.
        units: Every unit of the file, built without exclusions.
        logger: Caller's logger.

    Returns:
        The keys to exclude.
    """
    duplicated = {key: count for key, count in Counter(unit.key for unit in units).items() if count > 1}
    for key, count in duplicated.items():
        logger.warning(ConsoleFormatter.warning(f"Key '{key}' appears {count} times, each value is translated"))

    for key in excluded_keys:
        if key in duplicated:
            logger.warning(ConsoleFormatter.warning(f"Ignoring excluded key '{key}': it appears more than once"))

    return set(excluded_keys) - duplicated.keys()


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _nothing_recorded(path: str, locale: str) -> Mapping[str, str]:
    return {}


class Parser(ABC):
    """
    Abstract base class for localization source parsers.

    A parser converts a localization source file into a structured
    representation for translation. The parsed representation must
    retain sufficient context to efficiently write translated content
    back to the original source while preserving its structure and formatting.
    """

    def __init__(self, source_locale: str | None = None) -> None:
        """
        Args:
            source_locale: The source locale the configuration declares. Formats
                that carry their own source language check it against this one;
                the others ignore it.
        """
        self._source_locale: str | None = source_locale
        self._translated_from: Callable[[str, str], Mapping[str, str]] = _nothing_recorded
        self._options: Mapping[str, Any] = {}

    def use_options(self, options: Mapping[str, Any]) -> None:
        self._options = dict(options)

    def use_translated_from(self, lookup: Callable[[str, str], Mapping[str, str]]) -> None:
        self._translated_from = lookup

    def content_hash(self, source_path: Path) -> str:
        """Fingerprint of what the source file contributes to translation.

        The run lock compares it between runs to tell whether a source changed. The default hashes
        the whole file. Formats that keep other locales in the source file override it, so writing
        a translation doesn't make the source look changed.

        Args:
            source_path: Path to the localization source file.

        Returns:
            A hex digest that changes when the translatable content changes.
        """
        return hash_file_contents(source_path)

    def has_target(self, source_path: Path, destination: Path, locale: str, excluded_keys: list[str]) -> bool:
        """Whether the target for `locale` is already there.

        The run lock treats a target that is missing as stale. The default is whether the destination
        file exists. Formats that write every locale into the source file override it, since that file
        always exists.

        Args:
            source_path: Path to the localization source file.
            destination: Path the translation of `locale` is written to.
            locale: The target locale.
            excluded_keys: Resource keys that are left untranslated.

        Returns:
            True when there is nothing left to translate for `locale`.
        """
        return destination.exists()

    @abstractmethod
    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult | None:
        """Parse a localization source file.

        Args:
            source_path: Path to the localization source file.
            excluded_keys: Resource keys that should be omitted from the parsed
                output and excluded from translation.

        Returns:
            A structured `ParseResult` containing the extracted translation
            units and the metadata required for efficient write-back, or None
            when the file cannot be used as a source (the reason is logged).
        """
        raise NotImplementedError("The abstract method 'parse()' must be implemented by subclasses.")

    @abstractmethod
    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        """Clones a `ParseResult` object instance.

        Args:
            data: The `ParseResult` object.
            target_locale: The locale the clone will be translated into.

        Returns:
            A cloned copy of tje `ParseResult` object.
        """
