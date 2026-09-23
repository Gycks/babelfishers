from babelfishers.core.guards.placeholders import FORMAT_CATEGORIES
from babelfishers.models.guards import PlaceholderSpan
from babelfishers.models.translation_resource import TranslationResourceType


def _find_brace_spans(text: str) -> list[PlaceholderSpan]:
    """
    Balanced-brace scan. Catches every brace-delimited convention.

    Args:
        text: The text on which to run the search

    Returns:
        A list of `PlaceholderSpan` objects, one for each balanced
        brace-delimited region found. Each span contains the
    """

    spans: list[PlaceholderSpan] = []
    depth = 0
    start = -1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "'" and i + 1 < n and text[i + 1] in "{}#'|":
            # ICU quoted-literal span: only an apostrophe immediately followed by a
            # syntax character starts one (real ICU rule). Plain apostrophes in
            # ordinary text (contractions, possessives) must stay literal.
            j = text.find("'", i + 1)
            i = (j + 1) if j != -1 else n
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                i += 1
                continue
            depth -= 1
            if depth == 0 and start != -1:
                spans.append(
                    PlaceholderSpan(start=start, end=i + 1, matched_text=text[start : i + 1], category="brace_icu")
                )
                start = -1
        i += 1
    return spans


def find_placeholders(text: str, resource_type: TranslationResourceType) -> list[PlaceholderSpan]:
    occupied: list[tuple[int, int]] = []
    found: list[PlaceholderSpan] = []

    def free(s: int, e: int) -> bool:
        return not any(not (e <= os or s >= oe) for os, oe in occupied)

    for pattern in FORMAT_CATEGORIES.get(resource_type, []):
        for m in pattern.finditer(text):
            s, e = m.start(), m.end()
            if not free(s, e):
                continue
            occupied.append((s, e))
            (found.append(PlaceholderSpan(start=s, end=e, matched_text=m.group(0), category=pattern.pattern)))

    for span in _find_brace_spans(text):
        if free(span.start, span.end):
            occupied.append((span.start, span.end))
            found.append(span)

    found.sort(key=lambda p: p.start)
    return found
