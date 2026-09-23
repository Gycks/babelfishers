import re
from dataclasses import dataclass, field


_HEADER_RE = re.compile(r"^\{\s*([A-Za-z_]\w*)\s*,\s*(plural|selectordinal|select)\s*,\s*")
_OFFSET_RE = re.compile(r"^offset:\s*(-?\d+)\s*")
_SELECTOR_RE = re.compile(r"^(=\d+|[A-Za-z_]\w*)\s*")


@dataclass
class IcuArgument:
    arg_name: str
    arg_type: str
    offset: int | None
    categories: dict[str, str] = field(default_factory=dict)


def _find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    i = open_index
    n = len(text)
    while i < n:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_icu_argument(text: str) -> IcuArgument | None:
    """
    Parses a string that is, in its entirety, one ICU MessageFormat
    plural/selectordinal/select argument (e.g. Flutter ARB's
    "{count, plural, one{1 item} other{# items}}"), splitting it into its
    named categories. Returns None if the text isn't shaped like one.
    """
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    if _find_matching_brace(stripped, 0) != len(stripped) - 1:
        return None

    header = _HEADER_RE.match(stripped)
    if header is None:
        return None

    arg_name, arg_type = header.group(1), header.group(2)
    cursor = header.end()

    offset: int | None = None
    if arg_type in ("plural", "selectordinal"):
        offset_match = _OFFSET_RE.match(stripped[cursor:])
        if offset_match is not None:
            offset = int(offset_match.group(1))
            cursor += offset_match.end()

    categories: dict[str, str] = {}
    end = len(stripped) - 1

    while cursor < end:
        while cursor < end and stripped[cursor].isspace():
            cursor += 1
        if cursor >= end:
            break

        selector_match = _SELECTOR_RE.match(stripped[cursor:])
        if selector_match is None:
            return None
        selector = selector_match.group(1)
        cursor += selector_match.end()

        while cursor < end and stripped[cursor].isspace():
            cursor += 1
        if cursor >= end or stripped[cursor] != "{":
            return None

        close_index = _find_matching_brace(stripped, cursor)
        if close_index == -1:
            return None

        categories[selector] = stripped[cursor + 1 : close_index]
        cursor = close_index + 1

    if not categories:
        return None

    return IcuArgument(arg_name=arg_name, arg_type=arg_type, offset=offset, categories=categories)


def render_icu_argument(arg: IcuArgument) -> str:
    header = f"{arg.arg_name}, {arg.arg_type}, "
    offset = f"offset:{arg.offset} " if arg.offset is not None else ""
    body = " ".join(f"{selector} {{{message}}}" for selector, message in arg.categories.items())
    return f"{{{header}{offset}{body}}}"
