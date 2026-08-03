import json
import logging
import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


@register(TranslationResourceType.JSON)
class JSONParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._ALLOWED_EXTENSION: str = ".json"
        self._PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)]")

    @staticmethod
    def _make_write_back(d: dict[str, Any] | list[Any], key: str | int) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            d[key] = translated  # type: ignore[index]

        return write_back

    @staticmethod
    def _make_save(document: dict[str, Any]) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(document, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        raw: dict[str, Any] = json.loads(source_path.read_text(encoding="utf-8"))
        units: list[TranslationUnit] = []
        self._walk(raw, prefix="", units=units, excluded_keys=set(excluded_keys))

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(raw), document=raw)

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
                    units.append(
                        TranslationUnit(
                            unit_type=TranslationResourceType.JSON,
                            key=full_key,
                            source_text=v,
                            write_back=self._make_write_back(node, k),
                        )
                    )

                else:
                    self._walk(v, full_key, units, excluded_keys)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                full_key = f"{prefix}[{i}]"
                if full_key in excluded_keys:
                    continue

                if isinstance(item, str):
                    units.append(
                        TranslationUnit(
                            unit_type=TranslationResourceType.JSON,
                            key=full_key,
                            source_text=item,
                            write_back=self._make_write_back(node, i),
                        )
                    )

                else:
                    self._walk(item, full_key, units, excluded_keys)

    def clone(self, data: ParseResult) -> ParseResult:
        cloned_document = deepcopy(data.document)
        cloned_units = []

        for unit in data.units:
            unit_container, leaf_key = self._resolve_unit(cloned_document, unit.key)

            cloned_units.append(unit.model_copy(update={"write_back": self._make_write_back(unit_container, leaf_key)}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_document,
            save=self._make_save(cloned_document),
        )

    def _resolve_unit(self, document: Any, key: str) -> tuple[Any, str | int]:
        tokens = self._PATH_TOKEN_RE.findall(key)
        parts = [char if char else int(idx) for char, idx in tokens]
        container = document

        for part in parts[:-1]:
            container = container[part]

        return container, parts[-1]
