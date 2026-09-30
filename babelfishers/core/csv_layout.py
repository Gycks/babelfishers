import csv
import io
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from babel import Locale, UnknownLocaleError

from babelfishers.core.supported_cultures import SUPPORTED_CULTURES


BOM = "\ufeff"
_DELIMITERS = (",", ";", "\t", "|")
_ROLES: dict[str, frozenset[str]] = {
    "key": frozenset({"key", "keys", "id", "identifier", "name", "string_id", "string id"}),
    "value": frozenset({"value", "text", "translation", "string"}),
    "context": frozenset({"comment", "comments", "description", "context", "note", "notes", "developer_comments"}),
}
_NOT_LOCALES = frozenset({"root", "und"})
_TAG_IN_PARENTHESES = re.compile(r".*\(\s*([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)\s*\)")
_OPTION_NAMES = frozenset({"delimiter", "columns"})


@dataclass(frozen=True)
class CsvOptions:
    delimiter: str | None = None
    columns: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, options: Mapping[str, Any]) -> Self:
        unknown = set(options) - _OPTION_NAMES
        if unknown:
            raise ValueError(f"Unknown csv option(s): {', '.join(sorted(unknown))}")

        delimiter = options.get("delimiter")
        if delimiter is not None and delimiter not in _DELIMITERS:
            allowed = ", ".join(repr(d) for d in _DELIMITERS)
            raise ValueError(f"Invalid csv delimiter {delimiter!r}. Use one of {allowed}")

        columns = options.get("columns") or {}
        if not isinstance(columns, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in columns.items()
        ):
            raise ValueError("The csv option 'columns' must map a role or a locale to a column name")

        normalized: dict[str, str] = {}
        for role, column in columns.items():
            name = role.strip().lower().replace("_", "-")
            if name not in _ROLES and name not in SUPPORTED_CULTURES:
                raise ValueError(
                    f"'columns' entry '{role}' is neither key, value, context nor a supported locale. "
                    "Run `babelfishers locales` to list the supported ones"
                )
            normalized[name] = column

        return cls(delimiter=delimiter, columns=normalized)


@dataclass(frozen=True)
class CsvLayout:
    delimiter: str
    header: list[str]
    key: int
    context: int | None
    value: int | None = None
    locales: dict[str, int] = field(default_factory=dict)
    source_locale: str | None = None

    @property
    def wide(self) -> bool:
        return self.source_locale is not None

    @property
    def source(self) -> int:
        if self.source_locale is not None:
            return self.locales[self.source_locale]
        if self.value is None:
            raise ValueError("The layout has no source column")
        return self.value


def read_csv_text(path: Path) -> tuple[str, bool]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exe:
        raise ValueError(f"{path} is not valid UTF-8") from exe

    if text.startswith(BOM):
        return text[len(BOM) :], True
    return text, False


def _pick_delimiter(path: Path, text: str, options: CsvOptions) -> str:
    if options.delimiter is not None:
        return options.delimiter
    if path.suffix.lower() == ".tsv":
        return "\t"

    first_line = text.split("\n", 1)[0]
    counts = {delimiter: first_line.count(delimiter) for delimiter in _DELIMITERS}
    best = max(counts.values())
    if best == 0:
        return ","
    return next(delimiter for delimiter in _DELIMITERS if counts[delimiter] == best)


def _role(cell: str) -> str | None:
    name = cell.strip().lower()
    return next((role for role, names in _ROLES.items() if name in names), None)


def _locale(cell: str) -> str | None:
    name = cell.strip()
    match = _TAG_IN_PARENTHESES.fullmatch(name)
    tag = match.group(1) if match else name
    if not tag or tag.lower() in _NOT_LOCALES:
        return None

    try:
        Locale.parse(tag.replace("-", "_"))
    except (UnknownLocaleError, ValueError, TypeError):
        return None

    return tag.lower().replace("_", "-")


def detect_csv_layout(path: Path, source_locale: str, options: CsvOptions | None = None) -> CsvLayout:
    options = options or CsvOptions()
    text, _ = read_csv_text(path)
    delimiter = _pick_delimiter(path, text, options)

    header = next(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter), None)
    if not header or not any(cell.strip() for cell in header):
        raise ValueError(f"{path} has no header row. Its first row must name the columns")

    names = [cell.strip().lower() for cell in header]
    roles: dict[str, int] = {}
    locales: dict[str, int] = {}

    for name, column in options.columns.items():
        if column.strip().lower() not in names:
            raise ValueError(f"{path} has no column '{column}', which 'columns' maps '{name}' to")
        index = names.index(column.strip().lower())
        (roles if name in _ROLES else locales)[name] = index

    mapped = set(roles.values()) | set(locales.values())
    for index, cell in enumerate(header):
        if index in mapped:
            continue

        role = _role(cell)
        if role is not None:
            if role in roles:
                raise ValueError(f"{path} has more than one {role} column: '{header[roles[role]]}' and '{cell}'")
            roles[role] = index
            continue

        locale = _locale(cell)
        if locale is None:
            continue
        if locale not in SUPPORTED_CULTURES:
            raise ValueError(
                f"{path}: column '{cell.strip()}' is the locale '{locale}', which is not supported. "
                "Run `babelfishers locales` to list the supported ones, or map the columns with 'columns'"
            )
        if locale in locales:
            raise ValueError(f"{path} has more than one column for the locale '{locale}'")
        locales[locale] = index

    source = source_locale.lower()
    if "key" not in roles:
        if 0 in roles.values() or 0 in locales.values():
            raise ValueError(f"{path} has no key column. Name it 'key', or map it with 'columns'")
        roles["key"] = 0

    if source in locales:
        if "value" in roles:
            raise ValueError(
                f"{path} has both a '{header[locales[source]]}' and a '{header[roles['value']]}' column, "
                "so its layout is ambiguous. Map the columns with 'columns'"
            )
        return CsvLayout(
            delimiter=delimiter,
            header=header,
            key=roles["key"],
            context=roles.get("context"),
            locales=locales,
            source_locale=source,
        )

    if locales:
        found = ", ".join(header[index].strip() for index in locales.values())
        raise ValueError(
            f"{path} has locale columns ({found}) but none for the source locale '{source_locale}'. "
            "Add one, or map it with 'columns'"
        )

    if "value" in roles:
        return CsvLayout(
            delimiter=delimiter,
            header=header,
            key=roles["key"],
            context=roles.get("context"),
            value=roles["value"],
        )

    found = ", ".join(cell.strip() for cell in header)
    raise ValueError(
        f"Can't tell the layout of {path}: columns {found}. It needs a column for the source locale "
        f"'{source_locale}' (one column per locale) or a 'value' column (one file per locale). "
        "Map the columns with 'columns'"
    )
