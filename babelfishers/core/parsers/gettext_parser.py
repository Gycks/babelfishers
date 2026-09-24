import logging
import re
from collections.abc import Callable
from copy import deepcopy
from gettext import c2py
from pathlib import Path
from typing import Any

from babel import UnknownLocaleError
from babel.messages.plurals import get_plural

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
_NEWLINE_SEGMENT_RE = re.compile(r"[^\n]*\n|[^\n]+")
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
    def _meta_of(document: list[dict[str, Any]]) -> dict[str, Any]:
        for entry in document:
            if "__meta__" in entry:
                return entry
        return {"__meta__": True, "newline": "\n", "excluded_keys": []}

    @staticmethod
    def _header_of(document: list[dict[str, Any]]) -> dict[str, Any] | None:
        for entry in document:
            if "__meta__" not in entry and entry["msgid"] == "" and entry["msgctxt"] is None:
                return entry
        return None

    @staticmethod
    def _set_header_fields(header: str, fields: dict[str, str]) -> str:
        """Replace the named `Name: value` header lines, appending any the header lacks."""
        pending = {name.lower(): (name, value) for name, value in fields.items()}
        lines = []
        for line in header.splitlines():
            name, value = pending.pop(line.split(":", 1)[0].strip().lower(), (None, None))
            lines.append(line if name is None else f"{name}: {value}")
        lines.extend(f"{name}: {value}" for name, value in pending.values())
        return "".join(f"{line}\n" for line in lines)

    def _localize(self, document: list[dict[str, Any]], target_locale: str) -> int | None:
        """
        Point the header at `target_locale` and give every plural entry the target's
        number of `msgstr[n]` slots, using the gettext plural rules `pybabel init` writes.

        Returns the slot the target uses for n == 1, which takes the `msgid` text; the
        other slots take `msgid_plural`. None when the target has a single form for
        every count, in which case that form takes `msgid_plural`.
        """
        language = target_locale.replace("-", "_")
        fields = {"Language": language}
        singular_slot: int | None = 0

        try:
            plural = get_plural(language)
        except (UnknownLocaleError, ValueError):
            self._logger.warning(
                ConsoleFormatter.warning(
                    f"No gettext plural rule known for '{target_locale}', keeping the source Plural-Forms"
                )
            )
        else:
            fields["Plural-Forms"] = str(plural)
            singular_slot = c2py(plural.plural_expr)(1) if plural.num_plurals > 1 else None
            for entry in document:
                if "__meta__" not in entry and entry["msgid_plural"] is not None:
                    entry["msgstr_plural"] = {i: entry["msgstr_plural"].get(i, "") for i in range(plural.num_plurals)}

        header = self._header_of(document)
        if header is None:
            header = {
                "comments": [],
                "msgctxt": None,
                "msgid": "",
                "msgid_plural": None,
                "msgstr": "Content-Type: text/plain; charset=UTF-8\n",
                "msgstr_plural": {},
            }
            document.insert(0, header)
        header["msgstr"] = self._set_header_fields(header["msgstr"] or "", fields)

        return singular_slot

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
        """Like GNU gettext, end a line after every embedded newline, then wrap what is still too long."""
        if "\n" not in text[:-1]:
            single_line = f'{field_prefix} "{self._escape(text)}"'
            if len(single_line) <= width:
                return [single_line]

        lines = [f'{field_prefix} ""']
        for segment in _NEWLINE_SEGMENT_RE.findall(text):
            lines.extend(self._wrap_escaped(self._escape(segment), width))
        return lines

    @staticmethod
    def _wrap_escaped(escaped: str, width: int) -> list[str]:
        lines = []
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
            newline = self._meta_of(document)["newline"]
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

    def _build_units(self, document: list[dict[str, Any]], singular_slot: int | None) -> list[TranslationUnit]:
        excluded = set(self._meta_of(document)["excluded_keys"])

        units: list[TranslationUnit] = []
        for key, (entry, plural_index) in self._index_entries(document).items():
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
                source_text = (
                    entry["msgid"] if plural_index == singular_slot else (entry["msgid_plural"] or entry["msgid"])
                )
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

        return units

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        with source_path.open(encoding="utf-8", newline="") as handle:
            raw_text = handle.read()
        newline = detect_newline(raw_text)

        document = self._parse_entries(raw_text)
        document.append({"__meta__": True, "newline": newline, "excluded_keys": list(excluded_keys)})
        units = self._build_units(document, singular_slot=0)

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(document), document=document)

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        cloned_document: list[dict[str, Any]] = deepcopy(data.document)
        singular_slot = 0 if target_locale is None else self._localize(cloned_document, target_locale)

        return ParseResult(
            source_path=data.source_path,
            units=self._build_units(cloned_document, singular_slot),
            document=cloned_document,
            save=self._make_save(cloned_document),
        )
