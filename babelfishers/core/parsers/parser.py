from abc import ABC, abstractmethod
from pathlib import Path

from babelfishers.models.translations import ParseResult


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
