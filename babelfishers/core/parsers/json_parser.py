import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.parser_factory import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


@register(TranslationResourceType.JSON)
class JSONParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._ALLOWED_EXTENSION: str = ".json"

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        raw: dict[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
        units: list[TranslationUnit] = []
        self._walk(raw, prefix="", units=units, excluded_keys=set(excluded_keys))

        def save(destination: Path) -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=save)

    def _walk(
        self,
        node: Any,
        prefix: str,
        units: list[TranslationUnit],
        excluded_keys: set[str],
    ) -> None:

        if isinstance(node, dict):
            for k, v in node.items():
                full_key = f"{prefix}.{k}" if prefix else k
                if full_key in excluded_keys:
                    continue

                if isinstance(v, str):

                    def make_write_back(d: dict[str, Any], key: str) -> Callable[[str], None]:
                        def write_back(translated: str) -> None:
                            d[key] = translated

                        return write_back

                    units.append(
                        TranslationUnit(
                            unit_type=TranslationResourceType.JSON,
                            key=full_key,
                            source_text=v,
                            write_back=make_write_back(node, k),
                        )
                    )

                else:
                    self._walk(v, full_key, units, excluded_keys)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                self._walk(item, f"{prefix}[{i}]", units, excluded_keys)
