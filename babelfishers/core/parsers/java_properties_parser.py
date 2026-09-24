import logging
import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write, detect_newline


_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_ESCAPED_CHAR_RE = re.compile(r"\\(.)")
_UNESCAPE_MAP: dict[str, str] = {"n": "\n", "t": "\t", "r": "\r", "f": "\f"}


@register(TranslationResourceType.JAVA_PROPERTIES)
class JavaPropertiesParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".properties"

    @staticmethod
    def _ends_with_continuation(line: str) -> bool:
        count = 0
        for ch in reversed(line):
            if ch != "\\":
                break
            count += 1
        return count % 2 == 1

    def _read_logical_lines(self, raw_text: str) -> list[str]:
        raw_lines = raw_text.splitlines()
        logical_lines: list[str] = []
        buffer = ""
        continuing = False

        for raw_line in raw_lines:
            buffer = buffer + raw_line.lstrip() if continuing else raw_line
            if self._ends_with_continuation(buffer):
                buffer = buffer[:-1]
                continuing = True
                continue
            logical_lines.append(buffer)
            buffer = ""
            continuing = False

        if continuing:
            logical_lines.append(buffer)

        return logical_lines

    @staticmethod
    def _unescape(text: str) -> str:
        text = _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
        return _ESCAPED_CHAR_RE.sub(lambda m: _UNESCAPE_MAP.get(m.group(1), m.group(1)), text)

    @staticmethod
    def _escape_key(text: str) -> str:
        return text.replace("\\", "\\\\").replace(":", "\\:").replace("=", "\\=").replace(" ", "\\ ")

    @staticmethod
    def _escape_value(text: str) -> str:
        return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")

    @staticmethod
    def _split_line(stripped: str) -> tuple[str, str]:
        i = 0
        n = len(stripped)

        while i < n:
            ch = stripped[i]
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch in "=: \t":
                break
            i += 1

        key_raw = stripped[:i]

        while i < n and stripped[i] in " \t":
            i += 1
        if i < n and stripped[i] in "=:":
            i += 1
            while i < n and stripped[i] in " \t":
                i += 1

        value_raw = stripped[i:]
        return JavaPropertiesParser._unescape(key_raw), JavaPropertiesParser._unescape(value_raw)

    @staticmethod
    def _make_write_back(entry: dict[str, str]) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            entry["value"] = translated

        return write_back

    @staticmethod
    def _newline_of(document: list[dict[str, str]]) -> str:
        for entry in document:
            if entry["type"] == "meta":
                return entry["newline"]
        return "\n"

    def _make_save(self, document: list[dict[str, str]]) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            newline = self._newline_of(document)
            lines = [
                entry["text"]
                if entry["type"] == "raw"
                else f"{self._escape_key(entry['key'])}={self._escape_value(entry['value'])}"
                for entry in document
                if entry["type"] != "meta"
            ]

            def write(tmp: Path) -> None:
                with tmp.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(newline.join(lines) + newline)

            atomic_write(destination, write)

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        with source_path.open(encoding="utf-8", newline="") as handle:
            raw_text = handle.read()
        newline = detect_newline(raw_text)

        excluded = set(excluded_keys)
        seen_keys: set[str] = set()
        document: list[dict[str, str]] = []
        units: list[TranslationUnit] = []

        for line in self._read_logical_lines(raw_text):
            stripped = line.lstrip()
            if not stripped or stripped[0] in "#!":
                document.append({"type": "raw", "text": line})
                continue

            key, value = self._split_line(stripped)
            if key in seen_keys:
                self._logger.warning(ConsoleFormatter.warning(f"Duplicate properties key '{key}', keeping last"))
            seen_keys.add(key)

            entry: dict[str, str] = {"type": "entry", "key": key, "value": value}
            document.append(entry)

            if key in excluded or not value.strip():
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.JAVA_PROPERTIES,
                    key=key,
                    source_text=value,
                    write_back=self._make_write_back(entry),
                )
            )

        document.append({"type": "meta", "newline": newline})

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(document), document=document)

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        cloned_document: list[dict[str, str]] = deepcopy(data.document)

        index_by_key: dict[str, list[int]] = {}
        for i, entry in enumerate(cloned_document):
            if entry["type"] == "entry":
                index_by_key.setdefault(entry["key"], []).append(i)

        consumed: dict[str, int] = {}
        cloned_units = []
        for unit in data.units:
            occurrence = consumed.get(unit.key, 0)
            consumed[unit.key] = occurrence + 1
            entry_index = index_by_key[unit.key][occurrence]
            cloned_units.append(
                unit.model_copy(update={"write_back": self._make_write_back(cloned_document[entry_index])})
            )

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_document,
            save=self._make_save(cloned_document),
        )
