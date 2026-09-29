import logging
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path

from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


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


class Parser(ABC):
    """
    Abstract base class for localization source parsers.

    A parser converts a localization source file into a structured
    representation for translation. The parsed representation must
    retain sufficient context to efficiently write translated content
    back to the original source while preserving its structure and formatting.
    """

    @abstractmethod
    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        """Parse a localization source file.

        Args:
            source_path: Path to the localization source file.
            excluded_keys: Resource keys that should be omitted from the parsed
                output and excluded from translation.

        Returns:
            A structured `ParseResult` containing the extracted translation
            units and the metadata required for efficient write-back.
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
