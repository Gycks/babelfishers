import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.core.parsers.xml_support import inner_xml, parse_xml, parse_xml_string, serialize_xml, set_inner_xml
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


@register(TranslationResourceType.ANDROID_STRINGS)
class AndroidStringsParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._ALLOWED_EXTENSION: str = ".xml"

    def _collect_entries(self, root: Any) -> dict[str, Any]:
        entries: dict[str, Any] = {}

        def register_entry(key: str, element: Any) -> None:
            if key in entries:
                self._logger.warning(ConsoleFormatter.warning(f"Duplicate Android string key '{key}', keeping last"))
            entries[key] = element

        for string_el in root.findall("string"):
            name = string_el.get("name")
            if name is None:
                self._logger.warning(ConsoleFormatter.warning("Skipping <string> element with no 'name' attribute"))
                continue
            if string_el.get("translatable") == "false":
                continue
            register_entry(name, string_el)

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
                register_entry(f"{name}[{i}]", item_el)

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
                register_entry(f"{name}.{quantity}", item_el)

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
        excluded = set(excluded_keys)

        units: list[TranslationUnit] = []
        for key, element in entries.items():
            if key in excluded:
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

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(root), document=root)

    def clone(self, data: ParseResult) -> ParseResult:
        cloned_root = parse_xml_string(serialize_xml(data.document))
        entries = self._collect_entries(cloned_root)

        cloned_units = []
        for unit in data.units:
            cloned_units.append(unit.model_copy(update={"write_back": self._make_write_back(entries[unit.key])}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_root,
            save=self._make_save(cloned_root),
        )
