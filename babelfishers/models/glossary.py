import json
import logging
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel

from babelfishers.core.supported_cultures import SUPPORTED_CULTURES
from babelfishers.utils.console_formater import ConsoleFormatter

_logger: logging.Logger = logging.getLogger(__file__)


class GlossaryTerm(BaseModel):
    term: str
    translatable: bool
    case_sensitive: bool
    context: str
    translations: dict[str, str]


class Glossary(BaseModel):
    terms: list[GlossaryTerm]

    @classmethod
    def load(cls, file_path: str | None) -> Self | None:
        if file_path is None:
            return None

        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Could not find glossary file {file_path}")

        if path.suffix.strip().lower() != ".json":
            raise ValueError("Glossary must be in a JSON format")

        data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf8"))
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
            case_sensitive = entry.get("caseSensitive", True)
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
                    case_sensitive=case_sensitive,
                )
            )
        return cls(terms=results)
