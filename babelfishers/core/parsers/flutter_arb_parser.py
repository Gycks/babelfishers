import json
import logging
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from babelfishers.core.parsers.icu_plural import IcuArgument, parse_icu_argument, render_icu_argument
from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


@register(TranslationResourceType.FLUTTER_ARB)
class FlutterArbParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".arb"

    def _warn_on_duplicate_pairs(self, pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                self._logger.warning(ConsoleFormatter.warning(f"Duplicate ARB key '{key}', keeping last"))
            result[key] = value
        return result

    @staticmethod
    def _make_write_back(d: dict[str, Any] | list[Any], key: str | int) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            d[key] = translated  # type: ignore[index]

        return write_back

    @staticmethod
    def _make_icu_category_write_back(
        commit: Callable[[str], None], icu: IcuArgument, category: str
    ) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            icu.categories[category] = translated
            commit(render_icu_argument(icu))

        return write_back

    @staticmethod
    def _make_save(document: dict[str, Any]) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            atomic_write(
                destination,
                lambda tmp: tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"),
            )

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        raw: dict[str, Any] = json.loads(
            source_path.read_text(encoding="utf-8"), object_pairs_hook=self._warn_on_duplicate_pairs
        )
        units: list[TranslationUnit] = []
        self._walk(raw, prefix="", units=units, excluded_keys=set(excluded_keys))

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(raw), document=raw)

    def _emit_leaf(
        self,
        node: dict[str, Any] | list[Any],
        key: str | int,
        full_key: str,
        value: str,
        units: list[TranslationUnit],
        excluded_keys: set[str],
    ) -> None:
        icu = parse_icu_argument(value)
        if icu is None:
            if value.strip():
                units.append(
                    TranslationUnit(
                        unit_type=TranslationResourceType.FLUTTER_ARB,
                        key=full_key,
                        source_text=value,
                        write_back=self._make_write_back(node, key),
                    )
                )
            return

        commit = self._make_write_back(node, key)
        for category, message in icu.categories.items():
            category_key = f"{full_key}.{category}"
            if category_key in excluded_keys or not message.strip():
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.FLUTTER_ARB,
                    key=category_key,
                    source_text=message,
                    write_back=self._make_icu_category_write_back(commit, icu, category),
                )
            )

    def _walk(
        self,
        node: Any,
        prefix: str,
        units: list[TranslationUnit],
        excluded_keys: set[str],
    ) -> None:

        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and k.startswith("@"):
                    continue

                full_key = f"{prefix}.{k}" if prefix else k
                if full_key in excluded_keys:
                    continue

                if isinstance(v, str):
                    self._emit_leaf(node, k, full_key, v, units, excluded_keys)
                else:
                    self._walk(v, full_key, units, excluded_keys)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                full_key = f"{prefix}[{i}]"
                if full_key in excluded_keys:
                    continue

                if isinstance(item, str):
                    self._emit_leaf(node, i, full_key, item, units, excluded_keys)
                else:
                    self._walk(item, full_key, units, excluded_keys)

    def clone(self, data: ParseResult) -> ParseResult:
        cloned_document = deepcopy(data.document)

        rebuilt_units: list[TranslationUnit] = []
        self._walk(cloned_document, prefix="", units=rebuilt_units, excluded_keys=set())
        rebuilt_by_key = {unit.key: unit for unit in rebuilt_units}

        cloned_units = [
            unit.model_copy(update={"write_back": rebuilt_by_key[unit.key].write_back}) for unit in data.units
        ]

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_document,
            save=self._make_save(cloned_document),
        )
