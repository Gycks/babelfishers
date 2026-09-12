import logging
from collections.abc import Callable, Iterator
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Comment, Doctype, NavigableString, PageElement, Tag

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


@register(TranslationResourceType.HTML)
class HTMLParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._ALLOWED_EXTENSION: str = ".html"
        self._ignore: list[str] = ["style", "script", "head", "title", "meta", "link", "noscript"]

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(f"Parsing source {source_path}")

        if not source_path.suffixes[-1] == self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        soup = BeautifulSoup(source_path.read_text(encoding="utf-8"), "html.parser")
        excluded_elements = self._resolve_excluded_elements(soup, excluded_keys)

        units: list[TranslationUnit] = []
        self._walk(soup.descendants, units=units, excluded_elements=excluded_elements)

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(soup), document=soup)

    @staticmethod
    def _make_write_back(node: NavigableString) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            node.replace_with(translated)

        return write_back

    @staticmethod
    def _make_save(soup: BeautifulSoup) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(str(soup), encoding="utf-8")

        return save

    def _resolve_excluded_elements(self, soup: BeautifulSoup, excluded_keys: list[str]) -> set[Tag]:
        """Resolves `excluded_keys` config entries (CSS selectors) against the
        parsed document into the concrete elements they match."""

        excluded: set[Tag] = set()
        for selector in excluded_keys:
            try:
                excluded.update(soup.select(selector))
            except Exception as exc:
                self._logger.warning(
                    ConsoleFormatter.warning(f"Ignoring invalid excluded_keys selector '{selector}': {exc}")
                )

        return excluded

    def _walk(
        self,
        node: Iterator[PageElement],
        units: list[TranslationUnit],
        excluded_elements: set[Tag],
    ) -> None:
        for index, element in enumerate(node):
            if not isinstance(element, NavigableString) or not self._is_translatable_node(element, excluded_elements):
                continue

            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.HTML,
                    key=str(index),
                    source_text=str(element),
                    write_back=self._make_write_back(element),
                )
            )

    def _is_translatable_node(self, node: NavigableString, excluded_elements: set[Tag]) -> bool:
        if isinstance(node, Doctype):
            return False

        if isinstance(node, Comment):
            return False

        if not node.strip():
            return False

        for p in node.parents:
            if p in excluded_elements:
                return False

            if getattr(p, "name", None) in self._ignore:
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

    def clone(self, data: ParseResult) -> ParseResult:
        cloned_soup = BeautifulSoup(str(data.document), "html.parser")
        cloned_nodes = list(cloned_soup.descendants)

        cloned_units = []
        for unit in data.units:
            cloned_node = cloned_nodes[int(unit.key)]
            if not isinstance(cloned_node, NavigableString):
                raise ValueError(f"Expected NavigableString for unit key {unit.key}, got {type(cloned_node)}")

            cloned_units.append(unit.model_copy(update={"write_back": self._make_write_back(cloned_node)}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_soup,
            save=self._make_save(cloned_soup),
        )
