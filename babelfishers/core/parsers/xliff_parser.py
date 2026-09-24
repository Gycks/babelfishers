import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.core.parsers.xml_support import inner_xml, parse_xml, parse_xml_string, serialize_xml, set_inner_xml
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


@register(TranslationResourceType.XLIFF)
class XLIFFParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSIONS: tuple[str, ...] = (".xliff", ".xlf")

    @staticmethod
    def _qualifier(root: Any) -> Callable[[str], str]:
        namespace = root.tag.split("}")[0][1:] if root.tag.startswith("{") else None

        def qn(local: str) -> str:
            return f"{{{namespace}}}{local}" if namespace else local

        return qn

    def _register_entry(
        self,
        entries: dict[str, tuple[str, Any, str | None]],
        key: str,
        source_el: Any,
        target_el: Any,
        target_parent: Any,
        qn: Callable[[str], str],
        note_text: str | None,
    ) -> None:
        if source_el is None:
            self._logger.warning(ConsoleFormatter.warning(f"Skipping unit '{key}' with no <source>"))
            return

        if key in entries:
            self._logger.warning(ConsoleFormatter.warning(f"Duplicate unit id '{key}', keeping last"))

        source_text = inner_xml(source_el)
        if target_el is None and source_text.strip():
            target_el = etree.SubElement(target_parent, qn("target"))

        entries[key] = (source_text, target_el, note_text)

    def _collect_v1_units(
        self, file_el: Any, qn: Callable[[str], str], file_prefix: str, entries: dict[str, tuple[str, Any, str | None]]
    ) -> None:
        for trans_unit in file_el.iter(qn("trans-unit")):
            unit_id = trans_unit.get("id")
            if unit_id is None:
                self._logger.warning(ConsoleFormatter.warning("Skipping <trans-unit> element with no 'id' attribute"))
                continue

            note_el = trans_unit.find(qn("note"))
            self._register_entry(
                entries,
                f"{file_prefix}{unit_id}",
                trans_unit.find(qn("source")),
                trans_unit.find(qn("target")),
                trans_unit,
                qn,
                note_el.text if note_el is not None else None,
            )

    def _collect_v2_units(
        self, file_el: Any, qn: Callable[[str], str], file_prefix: str, entries: dict[str, tuple[str, Any, str | None]]
    ) -> None:
        for unit_el in file_el.iter(qn("unit")):
            unit_id = unit_el.get("id")
            if unit_id is None:
                self._logger.warning(ConsoleFormatter.warning("Skipping <unit> element with no 'id' attribute"))
                continue

            notes_el = unit_el.find(qn("notes"))
            note_text = None
            if notes_el is not None:
                first_note = notes_el.find(qn("note"))
                note_text = first_note.text if first_note is not None else None

            segments = unit_el.findall(qn("segment"))
            if not segments:
                self._logger.warning(ConsoleFormatter.warning(f"Skipping <unit id='{unit_id}'> with no <segment>"))
                continue

            for index, segment_el in enumerate(segments):
                key = f"{file_prefix}{unit_id}" if len(segments) == 1 else f"{file_prefix}{unit_id}[{index}]"
                self._register_entry(
                    entries,
                    key,
                    segment_el.find(qn("source")),
                    segment_el.find(qn("target")),
                    segment_el,
                    qn,
                    note_text,
                )

    def _collect_entries(self, root: Any, qn: Callable[[str], str]) -> dict[str, tuple[str, Any, str | None]]:
        entries: dict[str, tuple[str, Any, str | None]] = {}
        version = root.get("version", "1.2")
        files = root.findall(qn("file"))
        multi_file = len(files) > 1

        for file_index, file_el in enumerate(files):
            file_prefix = ""
            if multi_file:
                file_id = file_el.get("id") or file_el.get("original") or str(file_index)
                file_prefix = f"{file_id}:"

            if version.startswith("2."):
                self._collect_v2_units(file_el, qn, file_prefix, entries)
            else:
                self._collect_v1_units(file_el, qn, file_prefix, entries)

        return entries

    @staticmethod
    def _make_write_back(target_el: Any) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            set_inner_xml(target_el, translated)

        return write_back

    @staticmethod
    def _make_save(root: Any) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            atomic_write(destination, lambda tmp: tmp.write_text(serialize_xml(root), encoding="utf-8"))

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() not in self._ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file extension for {source_path}. Expected one of {self._ALLOWED_EXTENSIONS}")

        root = parse_xml(source_path)
        qn = self._qualifier(root)
        entries = self._collect_entries(root, qn)
        excluded = set(excluded_keys)

        units: list[TranslationUnit] = []
        for key, (source_text, target_el, context_hint) in entries.items():
            if key in excluded or target_el is None or not source_text.strip():
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.XLIFF,
                    key=key,
                    source_text=source_text,
                    context_hint=context_hint,
                    write_back=self._make_write_back(target_el),
                )
            )

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(root), document=root)

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        cloned_root = parse_xml_string(serialize_xml(data.document))
        qn = self._qualifier(cloned_root)
        entries = self._collect_entries(cloned_root, qn)

        cloned_units = []
        for unit in data.units:
            _, target_el, _ = entries[unit.key]
            if target_el is None:
                raise ValueError(f"Cloned document is missing a <target> for unit '{unit.key}'")
            cloned_units.append(unit.model_copy(update={"write_back": self._make_write_back(target_el)}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_root,
            save=self._make_save(cloned_root),
        )
