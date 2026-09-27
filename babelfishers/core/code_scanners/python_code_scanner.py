import ast
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from babel.messages.extract import DEFAULT_KEYWORDS, extract_python

from babelfishers.core.code_scanners.code_scanner import CodeScanner
from babelfishers.core.code_scanners.registry import register
from babelfishers.models.extract import (
    CodeLocation,
    Extract,
    ExtractType,
    ScannedString,
    ScanResult,
    SkippedCall,
)


_FLASK_BABEL_KEYWORDS: dict[str, Any] = {
    "lazy_gettext": None,
    "lazy_ngettext": (1, 2),
    "lazy_pgettext": ((1, "c"), 2),
    "lazy_npgettext": ((1, "c"), 2, 3),
}

_FSTRING_CALLS_HIDDEN_FROM_BABEL = sys.version_info < (3, 12)

# REMARK: DO NOT TOUCH. NEEDED FOR MYPY CHECKS
_RawCall = tuple[int | None, str, str | tuple[str | None, ...] | None, list[str]]


@register(ExtractType.PYTHON)
class PythonCodeScanner(CodeScanner):
    def __init__(self, extensions: tuple[str, ...] = (".py",)) -> None:
        super().__init__(extensions)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._keywords: dict[str, Any] = {**DEFAULT_KEYWORDS, **_FLASK_BABEL_KEYWORDS}

    def scan(self, extract: Extract) -> ScanResult:
        result = ScanResult()
        for path in self._code_files(extract):
            self._scan_file(path, extract, result)
        return result

    def _scan_file(self, path: Path, extract: Extract, result: ScanResult) -> None:
        self._logger.info(f"Scanning file {path}")

        location_path = path.relative_to(extract.root)
        source = path.read_text(encoding="utf-8", errors="replace")
        source_lines = source.splitlines()
        tree = self._get_syntax_tree(source)
        keywords = {**self._keywords, **self._aliases(tree)} if tree else self._keywords

        with path.open("rb") as file:
            calls = cast(
                Iterator[_RawCall],
                extract_python(file, keywords=keywords, comment_tags=[self._comment_tag], options={}),
            )
            for lineno, function, message, comments in calls:
                message_tuple = message if isinstance(message, tuple) else (message,)
                location = CodeLocation(path=location_path, line=lineno)
                self._record(
                    result,
                    extract.catalog_pattern,
                    message_tuple,
                    keywords[function],
                    comments or [],
                    location,
                    source_lines,
                )

        if tree is not None and _FSTRING_CALLS_HIDDEN_FROM_BABEL:
            for call, function in self._calls_in_fstrings(tree, keywords):
                values = tuple(
                    argument.value if isinstance(argument, ast.Constant) and isinstance(argument.value, str) else None
                    for argument in [*call.args, *call.keywords]
                )

                # The syntax tree has no comments, so the translator comment is read from the lines
                # above the call, the way Babel collects it: a block of # lines, from the one that
                # starts with the comment tag down to the call.
                block: list[str] = []
                index = call.lineno - 2
                while index >= 0 and source_lines[index].strip().startswith("#"):
                    block.insert(0, source_lines[index].strip().lstrip("#").strip())
                    index -= 1
                tagged = next((i for i, line in enumerate(block) if line.startswith(self._comment_tag)), None)
                translator_comments = block[tagged:] if tagged is not None else []

                location = CodeLocation(path=location_path, line=call.lineno)
                self._record(
                    result,
                    extract.catalog_pattern,
                    values,
                    keywords[function],
                    translator_comments,
                    location,
                    source_lines,
                )

    def _record(
        self,
        record: ScanResult,
        catalog: str,
        message: tuple[str | None, ...],
        message_specs: Any,
        comments: list[str],
        location: CodeLocation,
        source_lines: list[str],
    ) -> None:
        """
        Add one gettext call to the scan result, as a found string or as a skipped call.

        The call is skipped when its text, plural or context could not be read, because
        it is built at runtime, such as _(status). It is kept out of the catalog, where it
        would be a broken entry, and reported so the user knows it will not be translated.
        A call with an empty text, such as _(""), is dropped with a warning.

        Args:
            record: The scan result to add the call to.
            catalog: Pattern of the catalog the string belongs to.
            message: The call's arguments as Babel read them, in order.
            message_specs: The function's argument layout in Babel's keyword format, such as
                None for _(), (1, 2) for ngettext() or ((1, "c"), 2) for pgettext().
            comments: The translator comments above the call.
            location: Where the call is, relative to the extract's root.
            source_lines: The file's lines, to quote the call when it is skipped.
        """

        named_message = self._filter_as_named_values_only(message_specs, message)
        unreadable = [name for name, value in named_message.items() if value is None]
        if unreadable:
            code = source_lines[location.line - 1].strip() if location.line else "(line unknown)"
            reason = f"{' and '.join(unreadable)} built at runtime"
            record.skipped.append(SkippedCall(location=location, code=code, reason=reason))
            return

        value = named_message["text"]
        if not value:
            self._logger.warning(f"Nothing to translate. Location: {location}")
            return

        record.strings.append(
            ScannedString(
                catalog=catalog,
                comments=[comment.removeprefix(self._comment_tag).strip() for comment in comments],
                location=location,
                plural=named_message.get("plural"),
                context=named_message.get("context"),
                key=value,
                text=value,
            )
        )

    @staticmethod
    def _filter_as_named_values_only(spec: Any, values: tuple[str | None, ...]) -> dict[str, str | None]:
        """
        Name the arguments of a gettext call that matter: i.e. its text, and its plural and context.

        Arguments the spec does not list, such as the count in ngettext() or name=name for a
        placeholder, are left out, so a None among them is never mistaken for a missing text.

        Args:
            spec: The function's argument layout in Babel's keyword format, positions counted
                from 1: None for a single text argument, (1, 2) for a text and a plural, and
                (1, "c") inside the tuple for a context. For example ((1, "c"), 2) for pgettext().
            values: The call's arguments as Babel read them, in order. None marks an argument
                that is not a plain string.

        Returns:
            The named parts, for example {"context": "button", "text": "Checkout"} for
            pgettext("button", "Checkout"). A part is None when Babel could not read it, or
            when the call has fewer arguments than the spec expects.
        """
        positions = {1: "text"} if spec is None else {}
        names = ["text", "plural"]
        for position in spec or ():
            if isinstance(position, tuple):  # (1, 'c') marks the context
                positions[position[0]] = "context"
            else:
                positions[position] = names.pop(0)

        return {name: values[position - 1] if position <= len(values) else None for position, name in positions.items()}

    @staticmethod
    def _get_syntax_tree(source: str) -> ast.Module | None:
        try:
            return ast.parse(source)
        except (SyntaxError, ValueError):
            return None

    @staticmethod
    def _function_name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _aliases(self, tree: ast.Module) -> dict[str, Any]:
        """
        Find the names this file binds to a gettext function, such as an import alias.

        Babel recognizes calls by function name only, so after
        `from django.utils.translation import gettext_lazy as _l`, every _l("...") would be
        invisible to it. The names found here are passed to Babel as extra keywords, each with
        the argument layout of the function it stands for.

        Two forms are recognized:
            from gettext import gettext as tr      # an import with "as"
            tr = translation.gettext               # an assignment of a gettext function

        A hand-written wrapper, such as `def tr(text): return gettext(text)`, is not detected.

        Args:
            tree: The file's syntax tree.

        Returns:
            Each alias with the argument layout, in Babel's keyword format, of the function it
            stands for. For example {"_l": None, "_p": ((1, "c"), 2)}.
        """
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for name in node.names:
                    if name.asname and name.name in self._keywords:
                        aliases[name.asname] = self._keywords[name.name]
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                bound = self._function_name(node.value)
                if bound in self._keywords:
                    aliases[node.targets[0].id] = self._keywords[bound]
        return aliases

    def _calls_in_fstrings(self, tree: ast.Module, keywords: dict[str, Any]) -> list[tuple[ast.Call, str]]:
        """
        Find the gettext calls inside the braces of f-strings, such as f"{_('Hello')}".

        Args:
            tree: The file's syntax tree.
            keywords: The gettext functions to look for, including this file's aliases.

        Returns:
            Each call with the name of the function it calls, in the order they appear in the
            file. A call inside a nested f-string, which is walked twice, is returned once.
        """
        found: dict[int, tuple[ast.Call, str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            for part in node.values:
                if not isinstance(part, ast.FormattedValue):
                    continue
                for inner in ast.walk(part.value):
                    if isinstance(inner, ast.Call) and (name := self._function_name(inner.func)) in keywords:
                        found[id(inner)] = (inner, name)  # nested f-strings are walked twice
        return sorted(found.values(), key=lambda item: (item[0].lineno, item[0].col_offset))
