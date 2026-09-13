import logging
import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write


def _make_duplicate_key_warning_loader(logger: logging.Logger) -> type[yaml.SafeLoader]:
    class _DuplicateKeyWarningLoader(yaml.SafeLoader):  # type: ignore[misc]
        pass

    def construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in seen:
                line = node.start_mark.line + 1
                logger.warning(ConsoleFormatter.warning(f"Duplicate YAML key '{key}' at line {line}"))
            seen.add(key)

        mapping: dict[Any, Any] = yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
        return mapping

    _DuplicateKeyWarningLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )
    return _DuplicateKeyWarningLoader


@register(TranslationResourceType.YAML)
class YAMLParser(Parser):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__file__)
        self._PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)]")
        self._ALLOWED_EXTENSIONS: tuple[str, ...] = (".yaml", ".yml")

    @staticmethod
    def _make_write_back(d: dict[str, Any] | list[Any], key: str | int) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            d[key] = translated  # type: ignore[index]

        return write_back

    @staticmethod
    def _make_save(document: Any) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            atomic_write(
                destination,
                lambda tmp: tmp.write_text(
                    yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                ),
            )

        return save

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() not in self._ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file extension for {source_path}. Expected one of {self._ALLOWED_EXTENSIONS}")

        loader = _make_duplicate_key_warning_loader(self._logger)
        raw: Any = yaml.load(source_path.read_text(encoding="utf-8"), Loader=loader) or {}  # noqa: S506
        units: list[TranslationUnit] = []
        self._walk(raw, prefix="", units=units, excluded_keys=set(excluded_keys))

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(source_path=source_path, units=units, save=self._make_save(raw), document=raw)

    def _walk(
        self,
        node: Any,
        prefix: str,
        units: list[TranslationUnit],
        excluded_keys: set[str],
    ) -> None:

        if isinstance(node, dict):
            for k, v in node.items():
                full_key = f"{prefix}.{k}" if prefix else str(k)
                if full_key in excluded_keys:
                    continue

                if isinstance(v, str):
                    if v.strip():
                        units.append(
                            TranslationUnit(
                                unit_type=TranslationResourceType.YAML,
                                key=full_key,
                                source_text=v,
                                write_back=self._make_write_back(node, k),
                            )
                        )

                else:
                    self._walk(v, full_key, units, excluded_keys)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                full_key = f"{prefix}[{i}]"
                if full_key in excluded_keys:
                    continue

                if isinstance(item, str):
                    if item.strip():
                        units.append(
                            TranslationUnit(
                                unit_type=TranslationResourceType.YAML,
                                key=full_key,
                                source_text=item,
                                write_back=self._make_write_back(node, i),
                            )
                        )

                else:
                    self._walk(item, full_key, units, excluded_keys)

    def clone(self, data: ParseResult) -> ParseResult:
        cloned_document = deepcopy(data.document)
        cloned_units = []

        for unit in data.units:
            unit_container, leaf_key = self._resolve_unit(cloned_document, unit.key)

            cloned_units.append(unit.model_copy(update={"write_back": self._make_write_back(unit_container, leaf_key)}))

        return ParseResult(
            source_path=data.source_path,
            units=cloned_units,
            document=cloned_document,
            save=self._make_save(cloned_document),
        )

    def _resolve_unit(self, document: Any, key: str) -> tuple[Any, str | int]:
        tokens = self._PATH_TOKEN_RE.findall(key)
        parts: list[str | int] = [char if char else int(idx) for char, idx in tokens]
        container = document

        for part in parts[:-1]:
            container = container[part]

        return container, parts[-1]
