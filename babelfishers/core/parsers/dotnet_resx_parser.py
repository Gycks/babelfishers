import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree

from babelfishers.core.parsers.parser import Parser, excluded_keys_without_duplicates
from babelfishers.core.parsers.registry import register
from babelfishers.core.parsers.xml_support import is_cdata, parse_xml, parse_xml_string, serialize_xml
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


@register(TranslationResourceType.DOTNET_RESX)
class DotNetResxParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".resx"

    def _collect_entries(self, root: Any) -> list[tuple[str, Any, Any, Any]]:
        entries: list[tuple[str, Any, Any, Any]] = []

        for data_el in root.findall("data"):
            if data_el.get("type") is not None or data_el.get("mimetype") is not None:
                continue

            name = data_el.get("name")
            if name is None:
                self._logger.warning(ConsoleFormatter.warning("Skipping <data> element with no 'name' attribute"))
                continue

            value_el = data_el.find("value")
            if value_el is None:
                self._logger.warning(ConsoleFormatter.warning(f"Skipping <data name='{name}'> with no <value>"))
                continue

            entries.append((name, value_el, data_el.find("comment"), data_el))

        return entries

    @staticmethod
    def _make_write_back(value_el: Any, data_el: Any) -> Callable[[str], None]:
        preserve_cdata = is_cdata(value_el)
        space_attr = "{http://www.w3.org/XML/1998/namespace}space"

        def write_back(translated: str) -> None:
            value_el.text = etree.CDATA(translated) if preserve_cdata else translated
            if translated != translated.strip() and data_el.get(space_attr) != "preserve":
                data_el.set(space_attr, "preserve")

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

    def _build_units(self, entries: list[tuple[str, Any, Any, Any]], excluded_keys: set[str]) -> list[TranslationUnit]:
        units: list[TranslationUnit] = []
        for key, value_el, comment_el, data_el in entries:
            if key in excluded_keys:
                continue

            source_text = value_el.text or ""
            if not source_text.strip():
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.DOTNET_RESX,
                    key=key,
                    source_text=source_text,
                    context_hint=comment_el.text if comment_el is not None else None,
                    write_back=self._make_write_back(value_el, data_el),
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
