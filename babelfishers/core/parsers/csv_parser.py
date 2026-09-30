import csv
import hashlib
import io
import json
import logging
import threading
from collections.abc import Callable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path

from babelfishers.core.csv_layout import BOM, CsvLayout, CsvOptions, detect_csv_layout, read_csv_text
from babelfishers.core.parsers.parser import Parser, excluded_keys_without_duplicates, source_hash
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write, detect_newline, hash_file_contents


_ALLOWED_EXTENSIONS = (".csv", ".tsv")


@dataclass
class _Table:
    rows: list[list[str]]
    layout: CsvLayout
    newline: str
    bom: bool
    trailing_newline: bool


@dataclass(frozen=True)
class _Row:
    index: int
    key: str
    text: str
    context: str | None


@dataclass
class _Target:
    locale: str
    translated_from: Mapping[str, str]
    writes: dict[int, tuple[str, str]] = field(default_factory=dict)
    record: dict[str, str] = field(default_factory=dict)


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def _set_cell(row: list[str], index: int, value: str) -> None:
    if index >= len(row):
        row.extend([""] * (index + 1 - len(row)))
    row[index] = value


@register(TranslationResourceType.CSV)
class CSVParser(Parser):
    _SAVE_LOCK = threading.Lock()

    def __init__(self, source_locale: str | None = None) -> None:
        if source_locale is None:
            raise ValueError("A CSV parser needs the configured source locale")

        super().__init__(source_locale)
        self._source_locale: str = source_locale
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._tables: dict[Path, tuple[tuple[int, int], _Table]] = {}

    def content_hash(self, source_path: Path) -> str:
        try:
            table = self._cached_table(source_path)
        except ValueError:
            return hash_file_contents(source_path)

        layout = table.layout
        if not layout.wide:
            return hash_file_contents(source_path)

        payload = json.dumps(
            [
                layout.source_locale,
                [
                    [_cell(row, layout.key), _cell(row, layout.source), _cell(row, layout.context)]
                    for row in table.rows[1:]
                ],
            ],
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def has_target(self, source_path: Path, destination: Path, locale: str, excluded_keys: list[str]) -> bool:
        if not destination.exists():
            return False

        try:
            table = self._cached_table(source_path)
        except ValueError:
            return False

        if not table.layout.wide:
            return True
        if locale.lower() == table.layout.source_locale:
            return True

        target = _Target(locale, self._translated_from(str(source_path), locale))
        return not self._pending_rows(table, set(excluded_keys), target)

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file extension for {source_path}. Expected one of {_ALLOWED_EXTENSIONS}")

        table = self._cached_table(source_path)
        all_units = [self._unit(row) for row in self._rows(table, set())]
        excluded = excluded_keys_without_duplicates(excluded_keys, all_units, self._logger)
        units = [self._unit(row) for row in self._rows(table, excluded)]

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(
            source_path=source_path,
            units=units,
            document=table,
            save=self._save_before_clone,
            excluded_keys=excluded,
        )

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        if target_locale is None:
            raise ValueError("A CSV file can only be cloned for a target locale")

        table: _Table = data.document
        if table.layout.wide:
            return self._clone_wide(data, table, target_locale)
        return self._clone_narrow(data, table)

    def _read_table(self, path: Path) -> _Table:
        text, bom = read_csv_text(path)
        layout = detect_csv_layout(path, self._source_locale, CsvOptions.from_mapping(self._options))
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=layout.delimiter))
        return _Table(
            rows=rows,
            layout=layout,
            newline=detect_newline(text),
            bom=bom,
            trailing_newline=text.endswith(("\n", "\r")),
        )

    def _cached_table(self, path: Path) -> _Table:
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        key = path.resolve()

        cached = self._tables.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]

        table = self._read_table(path)
        self._tables[key] = (signature, table)
        return table

    def _rows(self, table: _Table, excluded_keys: set[str]) -> Iterator[_Row]:
        layout = table.layout
        for index, row in enumerate(table.rows[1:], start=1):
            key = _cell(row, layout.key).strip()
            text = _cell(row, layout.source)
            if not key:
                if text.strip():
                    self._logger.warning(ConsoleFormatter.warning(f"Skipping row {index + 1}: it has no key"))
                continue
            if key in excluded_keys or not text.strip():
                continue

            context = _cell(row, layout.context).strip() or None
            yield _Row(index, key, text, context)

    @staticmethod
    def _unit(row: _Row, write_back: Callable[[str], None] | None = None) -> TranslationUnit:
        return TranslationUnit(
            unit_type=TranslationResourceType.CSV,
            key=row.key,
            source_text=row.text,
            context_hint=row.context,
            write_back=write_back or CSVParser._write_back_before_clone,
        )

    def _pending_rows(self, table: _Table, excluded_keys: set[str], target: _Target) -> list[_Row]:
        column = table.layout.locales.get(target.locale.lower())
        pending: list[_Row] = []
        for row in self._rows(table, excluded_keys):
            current = _cell(table.rows[row.index], column)
            recorded = target.translated_from.get(row.key)
            if not current.strip() or (recorded is not None and recorded != source_hash(row.text)):
                pending.append(row)
        return pending

    def _clone_wide(self, data: ParseResult, table: _Table, target_locale: str) -> ParseResult:
        live = {unit.key for unit in data.units}
        translated_from = self._translated_from(str(data.source_path), target_locale)
        target = _Target(
            target_locale,
            translated_from,
            record={key: value for key, value in translated_from.items() if key in live},
        )

        units: list[TranslationUnit] = []
        if target.locale.lower() == table.layout.source_locale:
            self._logger.warning(
                ConsoleFormatter.warning(f"Skipping '{target_locale}': it is the source locale of {data.source_path}")
            )
        else:
            units = [
                self._unit(row, self._make_wide_write_back(target, row))
                for row in self._pending_rows(table, data.excluded_keys, target)
            ]

        return ParseResult(
            source_path=data.source_path,
            units=units,
            document=table,
            save=self._make_wide_save(target),
            excluded_keys=data.excluded_keys,
            translated_from=target.record,
        )

    @staticmethod
    def _make_wide_write_back(target: _Target, row: _Row) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            target.writes[row.index] = (row.key, translated)
            target.record[row.key] = source_hash(row.text)

        return write_back

    def _make_wide_save(self, target: _Target) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            with self._SAVE_LOCK:
                if not target.writes and destination.exists():
                    return

                current = self._read_table(destination)
                column = current.layout.locales.get(target.locale.lower())
                if column is None:
                    column = len(current.rows[0])
                    current.rows[0].append(target.locale)

                for index, (key, translated) in target.writes.items():
                    if index < len(current.rows) and _cell(current.rows[index], current.layout.key).strip() == key:
                        _set_cell(current.rows[index], column, translated)

                self._write(destination, current)

        return save

    def _clone_narrow(self, data: ParseResult, table: _Table) -> ParseResult:
        copy = replace(table, rows=deepcopy(table.rows))
        units = [
            self._unit(row, self._make_narrow_write_back(copy, row)) for row in self._rows(table, data.excluded_keys)
        ]
        return ParseResult(
            source_path=data.source_path,
            units=units,
            document=copy,
            save=lambda destination: self._write(destination, copy),
            excluded_keys=data.excluded_keys,
        )

    @staticmethod
    def _make_narrow_write_back(copy: _Table, row: _Row) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            _set_cell(copy.rows[row.index], copy.layout.source, translated)

        return write_back

    @staticmethod
    def _dump(table: _Table) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, delimiter=table.layout.delimiter, lineterminator=table.newline)
        writer.writerows(table.rows)
        text = buffer.getvalue()
        if not table.trailing_newline:
            text = text.removesuffix(table.newline)
        return (BOM if table.bom else "") + text

    def _write(self, destination: Path, table: _Table) -> None:
        text = self._dump(table)

        def write(tmp: Path) -> None:
            with tmp.open("w", encoding="utf-8", newline="") as handle:
                handle.write(text)

        atomic_write(destination, write)

    @staticmethod
    def _write_back_before_clone(translated: str) -> None:
        raise ValueError("The parsed file has no target locale, clone it for a locale first")

    @staticmethod
    def _save_before_clone(destination: Path) -> None:
        raise ValueError("The parsed file has no target locale, clone it for a locale first")
