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
from babelfishers.utils.utils import atomic_write, detect_newline


_STATEMENT_RE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+"(.*)"$')
_CONTINUATION_RE = re.compile(r'^"(.*)"$')
_ESCAPED_CHAR_RE = re.compile(r"\\(.)")
_UNESCAPE_MAP: dict[str, str] = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
_FLAGS_COMMENT_RE = re.compile(r"^#,\s*(.*)$")
_PO_WRAP_WIDTH = 77


@register(TranslationResourceType.GETTEXT)
class GettextParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".po"

    @staticmethod
    def _unescape(text: str) -> str:
        return _ESCAPED_CHAR_RE.sub(lambda m: _UNESCAPE_MAP.get(m.group(1), m.group(1)), text)

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")

    def _parse_entries(self, raw_text: str) -> list[dict[str, Any]]:
        raw_lines = raw_text.splitlines()
        document: list[dict[str, Any]] = []

        comments: list[str] = []
        current: dict[str, Any] | None = None
        last_field: str | None = None
        last_plural_index: int | None = None

        def flush() -> None:
            nonlocal current, comments
            if current is not None:
                document.append(current)
            current = None
            comments = []

        for line_number, raw_line in enumerate(raw_lines, start=1):
            stripped = raw_line.strip()

            if not stripped:
                flush()
                continue

            if stripped.startswith("#"):
                comments.append(raw_line)
                continue

            if current is None:
                current = {
                    "comments": comments,
                    "msgctxt": None,
                    "msgid": "",
                    "msgid_plural": None,
                    "msgstr": None,
                    "msgstr_plural": {},
                }
                comments = []

            match = _STATEMENT_RE.match(stripped)
            if match is not None:
                field = match.group(1)
                index_str = match.group(2)
                value = self._unescape(match.group(3))

                if field == "msgctxt":
                    current["msgctxt"] = value
                    last_field, last_plural_index = "msgctxt", None
                elif field == "msgid":
                    current["msgid"] = value
                    last_field, last_plural_index = "msgid", None
                elif field == "msgid_plural":
                    current["msgid_plural"] = value
                    last_field, last_plural_index = "msgid_plural", None
                elif index_str is not None:
                    current["msgstr_plural"][int(index_str)] = value
                    last_field, last_plural_index = "msgstr_plural", int(index_str)
                else:
                    current["msgstr"] = value
                    last_field, last_plural_index = "msgstr", None
                continue

            continuation = _CONTINUATION_RE.match(stripped)
            if continuation is not None and last_field is not None:
                value = self._unescape(continuation.group(1))
                if last_field == "msgstr_plural" and last_plural_index is not None:
                    current["msgstr_plural"][last_plural_index] += value
                elif last_field == "msgstr":
                    current["msgstr"] = (current["msgstr"] or "") + value
                elif last_field in ("msgctxt", "msgid", "msgid_plural"):
                    current[last_field] = current[last_field] + value
                continue

            self._logger.warning(
                ConsoleFormatter.warning(f"Ignoring unrecognized PO syntax at line {line_number}: {raw_line!r}")
            )

        flush()
        return document

    @staticmethod
    def _entry_key(entry: dict[str, Any]) -> str:
        return f"{entry['msgctxt']}\x04{entry['msgid']}" if entry["msgctxt"] else entry["msgid"]

    @staticmethod
    def _newline_of(document: list[dict[str, Any]]) -> str:
        for entry in document:
            if "__meta__" in entry:
                return str(entry["newline"])
        return "\n"

    def _index_entries(self, document: list[dict[str, Any]]) -> dict[str, tuple[dict[str, Any], int | None]]:
        index: dict[str, tuple[dict[str, Any], int | None]] = {}
        for entry in document:
            if "__meta__" in entry or not entry["msgid"].strip():
                continue

            base_key = self._entry_key(entry)
            if entry["msgid_plural"] is None:
                if base_key in index:
                    self._logger.warning(ConsoleFormatter.warning(f"Duplicate PO msgid '{base_key}', keeping last"))
                index[base_key] = (entry, None)
            else:
                for i in entry["msgstr_plural"]:
                    index[f"{base_key}[{i}]"] = (entry, i)

        return index

    @staticmethod
    def _context_hint(entry: dict[str, Any]) -> str | None:
        notes = [c[2:].strip() for c in entry["comments"] if c.startswith("#.")]
        return "\n".join(notes) if notes else None

    @staticmethod
    def _clear_fuzzy_flag(entry: dict[str, Any]) -> None:
        """A fresh translation is no longer just a `msgmerge`-suggested guess."""
        updated_comments = []
        for comment in entry["comments"]:
            match = _FLAGS_COMMENT_RE.match(comment)
            if match is None:
                updated_comments.append(comment)
                continue

            remaining_flags = [f.strip() for f in match.group(1).split(",") if f.strip() and f.strip() != "fuzzy"]
            if remaining_flags:
                updated_comments.append(f"#, {', '.join(remaining_flags)}")

        entry["comments"] = updated_comments

    @classmethod
    def _make_write_back_singular(cls, entry: dict[str, Any]) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            entry["msgstr"] = translated
            cls._clear_fuzzy_flag(entry)

        return write_back

    @classmethod
    def _make_write_back_plural(cls, entry: dict[str, Any], index: int) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            entry["msgstr_plural"][index] = translated
            cls._clear_fuzzy_flag(entry)

        return write_back

    def _wrap_po_field(self, field_prefix: str, text: str, width: int = _PO_WRAP_WIDTH) -> list[str]:
        escaped = self._escape(text)
        if len(f'{field_prefix} "{escaped}"') <= width:
            return [f'{field_prefix} "{escaped}"']

        lines = [f'{field_prefix} ""']
        remaining = escaped
        max_chunk = max(width - 2, 1)

        while remaining:
            chunk = remaining[:max_chunk]
            if len(remaining) > max_chunk:
                break_at = chunk.rfind(" ")
                if break_at > 0:
                    chunk = chunk[: break_at + 1]

            while chunk and chunk.endswith("\\") and not chunk.endswith("\\\\"):
                chunk = chunk[:-1]
            if not chunk:
                chunk = remaining[:1]

            lines.append(f'"{chunk}"')
            remaining = remaining[len(chunk) :]

        return lines

    def _make_save(self, document: list[dict[str, Any]]) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            newline = self._newline_of(document)
            blocks: list[str] = []
            for entry in document:
                if "__meta__" in entry:
                    continue
                lines = list(entry["comments"])
                if entry["msgctxt"] is not None:
                    lines.extend(self._wrap_po_field("msgctxt", entry["msgctxt"]))
                lines.extend(self._wrap_po_field("msgid", entry["msgid"]))
                if entry["msgid_plural"] is not None:
                    lines.extend(self._wrap_po_field("msgid_plural", entry["msgid_plural"]))
                    for i in sorted(entry["msgstr_plural"]):
                        lines.extend(self._wrap_po_field(f"msgstr[{i}]", entry["msgstr_plural"][i]))
                else:
                    lines.extend(self._wrap_po_field("msgstr", entry["msgstr"] or ""))
                blocks.append(newline.join(lines))

            def write(tmp: Path) -> None:
                with tmp.open("w", encoding="utf-8", newline="") as handle:
                    handle.write((newline * 2).join(blocks) + newline)

            atomic_write(destination, write)

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        with source_path.open(encoding="utf-8", newline="") as handle:
            raw_text = handle.read()
        newline = detect_newline(raw_text)

        document = self._parse_entries(raw_text)
        entries_index = self._index_entries(document)
        excluded = set(excluded_keys)

        units: list[TranslationUnit] = []
        for key, (entry, plural_index) in entries_index.items():
            if key in excluded:
                continue

            if plural_index is None:
                if not entry["msgid"].strip():
                    continue
                units.append(
                    TranslationUnit(
                        unit_type=TranslationResourceType.GETTEXT,
                        key=key,
                        source_text=entry["msgid"],
                        context_hint=self._context_hint(entry),
                        write_back=self._make_write_back_singular(entry),
                    )
                )
            else:
                source_text = entry["msgid"] if plural_index == 0 else (entry["msgid_plural"] or entry["msgid"])
                if not source_text.strip():
                    continue
                units.append(
                    TranslationUnit(
                        unit_type=TranslationResourceType.GETTEXT,
                        key=key,
                        source_text=source_text,
                        context_hint=self._context_hint(entry),
                        write_back=self._make_write_back_plural(entry, plural_index),
                    )
                )

        document.append({"__meta__": True, "newline": newline})

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(document), document=document)

    def clone(self, data: ParseResult) -> ParseResult:
        cloned_document: list[dict[str, Any]] = deepcopy(data.document)
        entries_index = self._index_entries(cloned_document)

        cloned_units = []
        for unit in data.units:
            entry, plural_index = entries_index[unit.key]
            write_back = (
                self._make_write_back_singular(entry)
                if plural_index is None
                else self._make_write_back_plural(entry, plural_index)
            )
            cloned_units.append(unit.model_copy(update={"write_back": write_back}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_document,
            save=self._make_save(cloned_document),
        )
