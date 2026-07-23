import json
import logging
import re
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.core.supported_cultures import SUPPORTED_CULTURES
from babelfishers.utils.console_formater import ConsoleFormatter


_logger: logging.Logger = logging.getLogger(__file__)


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
                rf"\b{re.escape(term.term)}\b",
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

    @classmethod
    def load(cls, file_path: str | None) -> Self | None:
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
            if "term" not in entry:
                _logger.warning(
                    ConsoleFormatter.warning(
                        f"Skipping glossary entry: missing required 'term' key. Entry contents: {entry}"
                    )
                )
                continue

            term = entry["term"]
            if not term or not term.strip():
                _logger.warning(
                    ConsoleFormatter.warning(
                        f"Skipping glossary entry: 'term' is blank or whitespace-only. Entry contents: {entry}"
                    )
                )
                continue

            translatable = entry.get("translatable", False)
            context = entry.get("context", "")
            translations: dict[str, str] = entry.get("translations", {})

            if not set(translations.keys()).issubset(SUPPORTED_CULTURES):
                raise ValueError(f"Invalid Glossary. Invalid language-code for {entry}")

            results.append(
                GlossaryTerm(
                    term=term,
                    translatable=translatable,
                    context=context,
                    translations=translations,
                )
            )
        return cls(terms=results)
