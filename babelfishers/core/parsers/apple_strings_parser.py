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


_TOKEN_RE = re.compile(
    r"/\*.*?\*/"
    r"|//[^\n]*"
    r'|"(?:[^"\\]|\\.)*"\s*=\s*"(?:[^"\\]|\\.)*"\s*;',
    re.DOTALL,
)
_ENTRY_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;$', re.DOTALL)
_ESCAPED_CHAR_RE = re.compile(r"\\(.)")
_UNESCAPE_MAP: dict[str, str] = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


@register(TranslationResourceType.APPLE_STRINGS)
class AppleStringsParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".strings"

    @staticmethod
    def _unescape(text: str) -> str:
        return _ESCAPED_CHAR_RE.sub(lambda m: _UNESCAPE_MAP.get(m.group(1), m.group(1)), text)

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")

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
            lines = []
            for entry in document:
                if entry["type"] == "meta":
                    continue
                if entry["type"] == "entry":
                    lines.append(f'"{self._escape(entry["key"])}" = "{self._escape(entry["value"])}";')
                else:
                    lines.append(entry["text"])

            def write(tmp: Path) -> None:
                with tmp.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(newline.join(lines) + newline)

            atomic_write(destination, write)

        return save

    def _parse_document(self, raw_text: str) -> tuple[list[dict[str, str]], list[str | None]]:
        document: list[dict[str, str]] = []
        context_hints: list[str | None] = []
        pending_comments: list[str] = []
        cursor = 0

        for match in _TOKEN_RE.finditer(raw_text):
            gap = raw_text[cursor : match.start()]
            if gap.strip():
                self._logger.warning(
                    ConsoleFormatter.warning(f"Preserving unrecognized content in .strings file: {gap.strip()!r}")
                )
                document.append({"type": "raw", "text": gap})
            cursor = match.end()

            token = match.group(0)
            if token.startswith("/*") or token.startswith("//"):
                document.append({"type": "comment", "text": token})
                pending_comments.append(token.strip("/* \t\n").rstrip("*/").strip())
                continue

            entry_match = _ENTRY_RE.match(token)
            if entry_match is None:
                continue

            key = self._unescape(entry_match.group(1))
            value = self._unescape(entry_match.group(2))
            document.append({"type": "entry", "key": key, "value": value})
            context_hints.append("\n".join(pending_comments) if pending_comments else None)
            pending_comments = []

        trailing = raw_text[cursor:]
        if trailing.strip():
            self._logger.warning(
                ConsoleFormatter.warning(
                    f"Preserving unrecognized trailing content in .strings file: {trailing.strip()!r}"
                )
            )
            document.append({"type": "raw", "text": trailing})

        return document, context_hints

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        with source_path.open(encoding="utf-8", newline="") as handle:
            raw_text = handle.read()
        newline = detect_newline(raw_text)

        document, context_hints = self._parse_document(raw_text)
        excluded = set(excluded_keys)

        seen_keys: set[str] = set()
        units: list[TranslationUnit] = []
        hint_index = 0
        for entry in document:
            if entry["type"] != "entry":
                continue

            context_hint = context_hints[hint_index]
            hint_index += 1

            if entry["key"] in seen_keys:
                self._logger.warning(ConsoleFormatter.warning(f"Duplicate .strings key '{entry['key']}', keeping last"))
            seen_keys.add(entry["key"])

            if entry["key"] in excluded or not entry["value"].strip():
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.APPLE_STRINGS,
                    key=entry["key"],
                    source_text=entry["value"],
                    context_hint=context_hint,
                    write_back=self._make_write_back(entry),
                )
            )

        document.append({"type": "meta", "newline": newline})

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(document), document=document)

    def clone(self, data: ParseResult) -> ParseResult:
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
