import json
import logging
import re
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.core.supported_cultures import SUPPORTED_CULTURES
from babelfishers.utils.console_formater import ConsoleFormatter


_logger: logging.Logger = logging.getLogger(__file__)

_TRUE_STRINGS = {"true", "1", "yes"}
_FALSE_STRINGS = {"false", "0", "no", ""}


class GlossaryTerm(BaseModel):
    term: str
    translatable: bool
    context: str
    translations: dict[str, str]


class GlossaryMatch(BaseModel):
    term: GlossaryTerm
    start: int
    end: int
    matched_text: str


class Glossary(BaseModel):
    terms: list[GlossaryTerm]

    _index: dict[str, GlossaryTerm] = {}

    def model_post_init(self, __context: Any) -> None:
        """
        Build lookup indexes after model initialization.
        """
        self._index = {}
        for term in self.terms:
            self._index[term.term.lower().strip()] = term

    def lookup(self, term: str) -> GlossaryTerm | None:
        """
        Look up the glossary index.

        Args:
            term: The exact term to search for.

        Returns:
            The matching GlossaryTerm if present, otherwise None.
        """
        return self._index.get(term.lower().strip())

    def find_matches(self, text: str) -> list[GlossaryMatch]:
        """
        Find glossary terms occurring inside the given text.

        Longer terms take precedence over shorter overlapping ones.
        A match is only counted if it isn't glued to another alphanumeric
        character on either side, regardless of whether the term itself
        starts or ends with a word character (so terms like "C++" are
        matched correctly, not just terms like "cat").

        Args:
            text: The exact text to search for.

        Returns:
            The list of matches retrieved.
        """
        matches: list[GlossaryMatch] = []
        occupied: list[tuple[int, int]] = []

        terms = sorted(
            self.terms,
            key=lambda t: len(t.term),
            reverse=True,
        )

        for term in terms:
            pattern = re.compile(
                rf"(?<!\w){re.escape(term.term)}(?!\w)",
                re.IGNORECASE,
            )

            for m in pattern.finditer(text):
                start = m.start()
                end = m.end()

                if any(not (end <= s or start >= e) for s, e in occupied):
                    continue

                occupied.append((start, end))

                matches.append(
                    GlossaryMatch(
                        term=term,
                        start=start,
                        end=end,
                        matched_text=m.group(0),
                    )
                )

        matches.sort(key=lambda m: m.start)

        return matches

    @staticmethod
    def _resolve_translatable(raw: Any) -> bool | None:
        """
        Coerce the "translatable" field into a real boolean.

        Returns None if the value can't be confidently interpreted as a
        boolean (the caller is responsible for warning and skipping).
        """
        if raw is None:
            return False

        if isinstance(raw, bool):
            return raw

        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in _TRUE_STRINGS:
                return True
            if normalized in _FALSE_STRINGS:
                return False

        return None

    @classmethod
    def load(cls, file_path: str | None) -> Self | None:
        """
        Loads the glossary

        Args:
            file_path: Path to the underlying glossary JSON file

        Returns:
            The parsed glossary, or None if no file path was given
        """
        if file_path is None:
            return None

        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Could not find glossary file {file_path}")

        if path.suffix.strip().lower() != ".json":
            raise ValueError("Glossary must be in a JSON format")

        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        results = []

        for entry in data:
            term = entry.get("term")
            if not isinstance(term, str) or not term.strip():
                _logger.warning(
                    ConsoleFormatter.warning(
                        f"Skipping glossary entry: 'term' is missing, blank, or not a string. Entry contents: {entry}"
                    )
                )
                continue

            translatable = cls._resolve_translatable(entry.get("translatable"))
            if translatable is None:
                _logger.warning(
                    ConsoleFormatter.warning(
                        f"Skipping glossary entry: 'translatable' is not a valid boolean. Entry contents: {entry}"
                    )
                )
                continue

            context = entry.get("context") or ""
            translations: dict[str, str] = entry.get("translations") or {}

            invalid_codes = set(translations.keys()) - set(SUPPORTED_CULTURES)
            if invalid_codes:
                _logger.warning(
                    ConsoleFormatter.warning(
                        f"Skipping glossary entry: unsupported language code(s) {sorted(invalid_codes)}. "
                        f"Entry contents: {entry}"
                    )
                )
                continue

            results.append(
                GlossaryTerm(
                    term=term,
                    translatable=translatable,
                    context=context,
                    translations=translations,
                )
            )
        return cls(terms=results)
