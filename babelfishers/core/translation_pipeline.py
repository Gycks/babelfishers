from pathlib import Path

from babelfishers.core.tm_store import TMStore
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary
from babelfishers.models.translations import ParseResult


class TranslationPipeline:
    def __init__(
        self, translation_engines: list[Engine], glossary: Glossary | None, translation_store: TMStore
    ) -> None:
        self._translation_engines: list[Engine] = translation_engines
        self._glossary: Glossary | None = glossary
        self._translation_store: TMStore = translation_store

    def run(self, parse_result: ParseResult, source_locale: str, target_locale: str, destination_path: Path) -> None:
        pass
