import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from babelfishers.core.parsers.parser import Parser, excluded_keys_without_duplicates
from babelfishers.core.parsers.registry import register
from babelfishers.core.parsers.xml_support import inner_xml, parse_xml, parse_xml_string, serialize_xml, set_inner_xml
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


@register(TranslationResourceType.ANDROID_STRINGS)
class AndroidStringsParser(Parser):
    def __init__(self, source_locale: str | None = None) -> None:
        super().__init__(source_locale)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".xml"

    def _collect_entries(self, root: Any) -> list[tuple[str, Any]]:
        entries: list[tuple[str, Any]] = []

        for string_el in root.findall("string"):
            name = string_el.get("name")
            if name is None:
                self._logger.warning(ConsoleFormatter.warning("Skipping <string> element with no 'name' attribute"))
                continue
            if string_el.get("translatable") == "false":
                continue
            entries.append((name, string_el))

        for array_el in root.findall("string-array"):
            name = array_el.get("name")
            if name is None:
                self._logger.warning(
                    ConsoleFormatter.warning("Skipping <string-array> element with no 'name' attribute")
                )
                continue
            if array_el.get("translatable") == "false":
                continue
            for i, item_el in enumerate(array_el.findall("item")):
                entries.append((f"{name}[{i}]", item_el))

        for plurals_el in root.findall("plurals"):
            name = plurals_el.get("name")
            if name is None:
                self._logger.warning(ConsoleFormatter.warning("Skipping <plurals> element with no 'name' attribute"))
                continue
            if plurals_el.get("translatable") == "false":
                continue
            for item_el in plurals_el.findall("item"):
                quantity = item_el.get("quantity")
                if quantity is None:
                    self._logger.warning(
                        ConsoleFormatter.warning(f"Skipping <item> in <plurals name='{name}'> with no 'quantity'")
                    )
                    continue
                entries.append((f"{name}.{quantity}", item_el))

        return entries

    @staticmethod
    def _make_write_back(element: Any) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            set_inner_xml(element, translated)

        return write_back

    @staticmethod
    def _make_save(root: Any) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            atomic_write(destination, lambda tmp: tmp.write_text(serialize_xml(root), encoding="utf-8"))

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        root = parse_xml(source_path)
        entries = self._collect_entries(root)
        excluded = excluded_keys_without_duplicates(excluded_keys, self._build_units(entries, set()), self._logger)
        units = self._build_units(entries, excluded)

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(
            source_path=source_path, units=units, save=self._make_save(root), document=root, excluded_keys=excluded
        )

    def _build_units(self, entries: list[tuple[str, Any]], excluded_keys: set[str]) -> list[TranslationUnit]:
        units: list[TranslationUnit] = []
        for key, element in entries:
            if key in excluded_keys:
                continue

            source_text = inner_xml(element)
            if not source_text.strip():
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.ANDROID_STRINGS,
                    key=key,
                    source_text=source_text,
                    write_back=self._make_write_back(element),
                )
            )

        return units

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        cloned_root = parse_xml_string(serialize_xml(data.document))

        return ParseResult(
            source_path=data.source_path,
            units=self._build_units(self._collect_entries(cloned_root), data.excluded_keys),
            document=cloned_root,
            save=self._make_save(cloned_root),
            excluded_keys=data.excluded_keys,
        )
