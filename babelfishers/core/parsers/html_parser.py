import logging
from collections.abc import Callable
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Comment, Doctype, NavigableString, PageElement, Tag

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


_INLINE_TAGS = {
    "a", "abbr", "b", "bdi", "bdo", "br", "button", "cite", "code", "data",
    "del", "dfn", "em", "i", "img", "input", "ins", "kbd", "label", "mark",
    "output", "q", "s", "samp", "select", "small", "span", "strong", "sub",
    "sup", "textarea", "time", "u", "var", "wbr",
}  # fmt: skip

_ATTRIBUTE_TARGETS: dict[str, tuple[str, ...]] = {
    "img": ("alt",),
    "area": ("alt",),
    "input": ("placeholder",),
    "textarea": ("placeholder",),
}
_UNIVERSAL_ATTRIBUTES: tuple[str, ...] = ("title",)


@register(TranslationResourceType.HTML)
class HTMLParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".html"
        self._ignore: list[str] = ["style", "script", "head", "title", "meta", "link", "noscript"]

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        """
        `excluded_keys` is part of the shared `Parser` contract but unused
        here: HTML exclusion is decided in-source via `translate="no"` and
        `class="notranslate"`, not via out-of-band config (see `_is_translatable_element`).
        """
        self._logger.info(f"Parsing source {source_path}")

        if not source_path.suffixes[-1] == self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        soup = BeautifulSoup(source_path.read_text(encoding="utf-8"), "html.parser")
        positions = self._index_positions(soup)

        units: list[TranslationUnit] = []
        self._walk_attributes(soup, positions, units)
        self._walk_blocks(soup, positions, units)

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(soup), document=soup)

    @staticmethod
    def _index_positions(soup: BeautifulSoup) -> dict[int, int]:
        return {id(element): index for index, element in enumerate(soup.descendants)}

    def _is_translatable_element(self, start: Tag) -> bool:
        for p in (start, *start.parents):
            if getattr(p, "name", None) in self._ignore:
                return False

            classes = p.get("class") if hasattr(p, "get") else None
            if classes and "notranslate" in classes:
                return False

            translate = p.get("translate") if hasattr(p, "get") else None
            if translate is not None:
                if not isinstance(translate, str):
                    translate = " ".join(translate)
                translate = translate.strip().lower()
                if translate == "no":
                    return False
                if translate == "yes":
                    return True

        return True

    @staticmethod
    def _make_attribute_write_back(element: Tag, attr_name: str) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            element[attr_name] = translated

        return write_back

    def _walk_attributes(self, soup: BeautifulSoup, positions: dict[int, int], units: list[TranslationUnit]) -> None:
        for element in soup.descendants:
            if not isinstance(element, Tag):
                continue

            for attr_name in _ATTRIBUTE_TARGETS.get(element.name, ()) + _UNIVERSAL_ATTRIBUTES:
                value = element.get(attr_name)
                if not isinstance(value, str) or not value.strip():
                    continue

                if not self._is_translatable_element(element):
                    continue

                units.append(
                    TranslationUnit(
                        unit_type=TranslationResourceType.HTML,
                        key=f"{positions[id(element)]}@{attr_name}",
                        source_text=value,
                        write_back=self._make_attribute_write_back(element, attr_name),
                    )
                )

    @staticmethod
    def _is_mergeable(node: PageElement) -> bool:
        if isinstance(node, (Comment, Doctype)):
            return False
        if isinstance(node, NavigableString):
            return True
        return isinstance(node, Tag) and node.name in _INLINE_TAGS

    @staticmethod
    def _make_block_write_back(run_nodes: list[PageElement]) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            fragment = BeautifulSoup(translated, "html.parser")
            new_nodes = list(fragment.contents)

            anchor = run_nodes[0]
            for new_node in new_nodes:
                anchor.insert_before(new_node)
            for old_node in run_nodes:
                old_node.extract()

        return write_back

    @staticmethod
    def _visible_text(nodes: list[PageElement]) -> str:
        return "".join(node.get_text() if isinstance(node, Tag) else str(node) for node in nodes)

    def _walk_blocks(self, container: Tag, positions: dict[int, int], units: list[TranslationUnit]) -> None:
        run_nodes: list[PageElement] = []

        def flush() -> None:
            nonlocal run_nodes
            if run_nodes and self._visible_text(run_nodes).strip():
                units.append(
                    TranslationUnit(
                        unit_type=TranslationResourceType.HTML,
                        key=str(positions[id(run_nodes[0])]),
                        source_text="".join(str(node) for node in run_nodes),
                        write_back=self._make_block_write_back(list(run_nodes)),
                    )
                )
            run_nodes = []

        for child in list(container.contents):
            if isinstance(child, (Comment, Doctype)):
                flush()
                continue

            if isinstance(child, NavigableString):
                if self._is_translatable_element(container):
                    run_nodes.append(child)
                else:
                    flush()
                continue

            if not isinstance(child, Tag):
                continue

            if child.name in _INLINE_TAGS:
                if self._is_translatable_element(child):
                    run_nodes.append(child)
                else:
                    flush()
                continue

            flush()
            self._walk_blocks(child, positions, units)

        flush()

    @staticmethod
    def _make_save(soup: BeautifulSoup) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            atomic_write(destination, lambda tmp: tmp.write_text(str(soup), encoding="utf-8"))

        return save

    @staticmethod
    def _is_marked_no_translate(node: PageElement) -> bool:
        if not isinstance(node, Tag):
            return False

        classes = node.get("class")
        if classes and "notranslate" in classes:
            return True

        translate = node.get("translate")
        if not isinstance(translate, str):
            translate = " ".join(translate) if translate else ""
        return translate.strip().lower() == "no"

    @classmethod
    def _collect_run(cls, anchor: PageElement) -> list[PageElement]:
        nodes = [anchor]
        sibling = anchor.next_sibling
        while sibling is not None and cls._is_mergeable(sibling) and not cls._is_marked_no_translate(sibling):
            nodes.append(sibling)
            sibling = sibling.next_sibling
        return nodes

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        cloned_soup = BeautifulSoup(str(data.document), "html.parser")
        cloned_nodes = list(cloned_soup.descendants)

        cloned_units = []
        for unit in data.units:
            if "@" in unit.key:
                index_str, attr_name = unit.key.split("@", 1)
                element = cloned_nodes[int(index_str)]
                if not isinstance(element, Tag):
                    raise ValueError(f"Expected Tag for unit key {unit.key}, got {type(element)}")
                write_back = self._make_attribute_write_back(element, attr_name)
            else:
                anchor = cloned_nodes[int(unit.key)]
                write_back = self._make_block_write_back(self._collect_run(anchor))

            cloned_units.append(unit.model_copy(update={"write_back": write_back}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_soup,
            save=self._make_save(cloned_soup),
        )
