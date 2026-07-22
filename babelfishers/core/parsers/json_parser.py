import logging
from pathlib import Path

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.parser_factory import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult
from babelfishers.utils.console_formater import ConsoleFormatter


@register(TranslationResourceType.JSON)
class JSONParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
