import hashlib
import json
import logging
import threading
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from babelfishers.core.guards.cldr import required_plural_categories
from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write, hash_file_contents


_INDENT = "  "
_TRANSLATED = "translated"
_CATEGORY_ORDER = ("zero", "one", "two", "few", "many", "other")

# A translation to write: the string's key and the path, inside the target localization, of the
# `stringUnit` that holds it (`("variations", "plural", "one", "stringUnit")`).
_Write = tuple[str, tuple[str, ...]]
_Writes = dict[_Write, str]


# Segments of a path after which comes the name of a device or a substitution.
_NAMED_BY = ("device", "substitutions")


def _label(prefix: tuple[str, ...]) -> str:
    """The names (devices, substitutions) along `prefix`, dotted: `("variations", "device", "mac")` gives `mac`."""
    return ".".join(name for before, name in zip(prefix, prefix[1:], strict=False) if before in _NAMED_BY)


@dataclass(frozen=True)
class _PlainPart:
    """A `stringUnit` found at `prefix`, the path of its node inside the source localization."""

    text: str
    prefix: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PluralPart:
    """The plural categories of the node at `prefix`, which is the source localization, a device or a substitution."""

    prefix: tuple[str, ...]
    texts: dict[str, str]


@register(TranslationResourceType.XCSTRINGS)
class XCStringParser(Parser):
    # Every locale of a catalog is written into the same file, and the runtime translates locales
    # concurrently, so the read-merge-write of a save must not interleave with another save.
    _SAVE_LOCK = threading.Lock()

    def __init__(self, source_locale: str | None = None) -> None:
        super().__init__(source_locale)
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._ALLOWED_EXTENSION: str = ".xcstrings"

    def content_hash(self, source_path: Path) -> str:
        """
        Hashes only what decides the units: the source language and, per string, its comment,
        flags and source localization. The other locales live in the same file and change with
        every run, so they are left out.
        """
        try:
            catalog = self._load_catalog(source_path)
        except ValueError:
            return hash_file_contents(source_path)

        source_locale = catalog.get("sourceLanguage")
        source_parts: dict[str, Any] = {}
        for key, entry in (catalog.get("strings") or {}).items():
            if not isinstance(entry, dict):
                source_parts[key] = entry
                continue

            localizations = entry.get("localizations")
            source_parts[key] = {
                "comment": entry.get("comment"),
                "shouldTranslate": entry.get("shouldTranslate"),
                "extractionState": entry.get("extractionState"),
                "source": localizations.get(source_locale) if isinstance(localizations, dict) else None,
            }

        payload = json.dumps(
            {"sourceLanguage": source_locale, "strings": source_parts}, sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def has_target(self, source_path: Path, destination: Path, locale: str, excluded_keys: list[str]) -> bool:
        """
        The catalog is its own destination and always exists, so ask it instead: the target is there
        when no string it would translate still lacks it. Warnings stay off, `parse` gives them.
        """
        if not destination.exists():
            return False

        try:
            catalog = self._load_catalog(destination)
        except ValueError:
            return False

        source_locale = catalog.get("sourceLanguage")
        if not isinstance(source_locale, str):
            return False

        if locale.lower() == source_locale.lower():
            return True

        return not self._build_units(catalog, source_locale, set(excluded_keys), locale, {}, warn=False)

    def parse(self, source_path: Path, excluded_keys: list[str]) -> ParseResult | None:
        self._logger.info(ConsoleFormatter.info(f"Parsing source {source_path}"))

        if source_path.suffix.lower() != self._ALLOWED_EXTENSION:
            raise ValueError(f"Invalid file extension for {source_path}. Expected {self._ALLOWED_EXTENSION}")

        catalog = self._load_catalog(source_path)
        raw_source_locale = catalog.get("sourceLanguage")
        if raw_source_locale is None:
            self._logger.error(ConsoleFormatter.error(f"{source_path} has no 'sourceLanguage', skipping the file"))
            return None

        if raw_source_locale.lower() != self._source_locale.lower():
            self._logger.error(
                ConsoleFormatter.error(
                    f"{source_path} declares '{raw_source_locale}' as its source language, "
                    f"but the configured source locale is '{self._source_locale}', skipping the file"
                )
            )
            return None

        excluded = set(excluded_keys)
        units = self._build_units(catalog, raw_source_locale, excluded)

        self._logger.info(ConsoleFormatter.success(f"Successfully parsed source {source_path}"))
        return ParseResult(
            source_path=source_path,
            units=units,
            document=catalog,
            save=self._save_before_clone,
            excluded_keys=excluded,
        )

    @staticmethod
    def _load_catalog(source_path: Path) -> dict[str, Any]:
        try:
            catalog = json.loads(source_path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exe:
            raise ValueError(f"{source_path} is not valid UTF-8") from exe
        except json.JSONDecodeError as exe:
            raise ValueError(f"{source_path} is not valid JSON: {exe}") from exe

        if not isinstance(catalog, dict):
            raise ValueError(f"{source_path} is not a string catalog: expected a JSON object at the top level")
        if not isinstance(catalog.get("strings", {}), dict):
            raise ValueError(f"{source_path} is not a valid string catalog: 'strings' must be an object")

        return catalog

    def _warn(self, warn: bool, message: str) -> None:
        if warn:
            self._logger.warning(ConsoleFormatter.warning(message))

    def _plural_texts(self, key: str, plural: Any, warn: bool) -> dict[str, str] | None:
        """The text of every category of a `plural` node. None when the node can't be used."""
        if not isinstance(plural, dict):
            self._warn(warn, f"Skipping '{key}': its plural variations are not an object")
            return None

        texts: dict[str, str] = {}
        for category, leaf in plural.items():
            string_unit = leaf.get("stringUnit") if isinstance(leaf, dict) else None
            value = string_unit.get("value") if isinstance(string_unit, dict) else None
            if not isinstance(value, str):
                self._warn(warn, f"Skipping '{key}': the source value of its '{category}' form is not text")
                return None
            texts[category] = value

        return texts

    def _collect_parts(
        self, key: str, node: Any, prefix: tuple[str, ...], warn: bool
    ) -> list[_PlainPart | _PluralPart] | None:
        """
        What the localization node at `prefix` has to translate: its `stringUnit`, its plural
        categories, and, going down, what its device variations and substitutions have.
        None when the string can't be used.
        """
        if not isinstance(node, dict):
            self._warn(warn, f"Skipping '{key}': a source localization is not an object")
            return None

        parts: list[_PlainPart | _PluralPart] = []

        variations = node.get("variations")
        if variations is not None:
            if not isinstance(variations, dict) or len(variations) != 1 or not {"plural", "device"} & set(variations):
                self._warn(warn, f"Skipping '{key}': only plural and device variations are supported")
                return None

            if "plural" in variations:
                texts = self._plural_texts(key, variations["plural"], warn)
                if texts is None:
                    return None
                if texts:
                    parts.append(_PluralPart(prefix, texts))
            else:
                devices = variations["device"]
                if not isinstance(devices, dict):
                    self._warn(warn, f"Skipping '{key}': its device variations are not an object")
                    return None
                for name, child in devices.items():
                    found = self._collect_parts(key, child, (*prefix, "variations", "device", name), warn)
                    if found is None:
                        return None
                    parts.extend(found)

        if "stringUnit" in node:
            value = node["stringUnit"].get("value") if isinstance(node["stringUnit"], dict) else None
            if not isinstance(value, str):
                self._warn(warn, f"Skipping '{key}': its source value is not text")
                return None
            parts.append(_PlainPart(value, prefix))

        substitutions = node.get("substitutions")
        if isinstance(substitutions, dict):
            for name, substitution in substitutions.items():
                found = self._collect_parts(key, substitution, (*prefix, "substitutions", name), warn)
                if found is None:
                    return None
                parts.extend(found)

        return parts

    def _source_parts(
        self, key: str, entry: dict[str, Any], source_locale: str, warn: bool = True
    ) -> list[_PlainPart | _PluralPart] | None:
        """What the source localization of one string has to translate. None when the string is skipped."""
        localizations = entry.get("localizations")
        source = localizations.get(source_locale) if isinstance(localizations, dict) else None

        # Without a source localization, the key is the source text.
        if source is None:
            return [_PlainPart(key)]

        parts = self._collect_parts(key, source, (), warn)
        if parts is not None and not parts:
            self._warn(warn, f"Skipping '{key}': its source localization has nothing to translate")
            return None

        return parts

    @staticmethod
    def _leaf_needs_translation(leaf: Any) -> bool:
        """Whether a node holding a `stringUnit` still lacks a usable value: absent, empty, new or in review."""
        string_unit = leaf.get("stringUnit") if isinstance(leaf, dict) else None
        if not isinstance(string_unit, dict):
            return True

        value = string_unit.get("value")
        return not (string_unit.get("state") == _TRANSLATED and isinstance(value, str) and value.strip())

    @staticmethod
    def _node_at(target: Any, path: tuple[str, ...]) -> Any:
        node = target
        for segment in path:
            node = node.get(segment) if isinstance(node, dict) else None
        return node

    def _is_left_alone(self, target: dict[str, Any], path: tuple[str, ...]) -> bool:
        """
        Whether the target already has a different shape along `path` that isn't ours to change:
        a translated plain value where the source varies, or variations of another kind.
        """
        node: Any = target
        for index, segment in enumerate(path):
            if segment == "variations" and isinstance(node, dict) and index + 1 < len(path):
                variations = node.get("variations")
                if variations is None:
                    if not self._leaf_needs_translation(node):
                        return True
                elif not isinstance(variations, dict) or path[index + 1] not in variations:
                    return True

            node = node.get(segment) if isinstance(node, dict) else None

        return False

    def _pending_items(
        self, entry: dict[str, Any], target_locale: str, part: _PlainPart | _PluralPart
    ) -> list[tuple[tuple[str, ...], str, str]]:
        """The (path, label, source text) triples of `part` the target still lacks."""
        localizations = entry.get("localizations")
        target = localizations.get(target_locale) if isinstance(localizations, dict) else None
        target = target if isinstance(target, dict) else {}
        label = _label(part.prefix)

        if isinstance(part, _PlainPart):
            node = self._node_at(target, part.prefix)
            # A target the translator made vary by plural or device is left alone.
            if self._is_left_alone(target, part.prefix) or (isinstance(node, dict) and "variations" in node):
                return []
            if not self._leaf_needs_translation(node):
                return []
            return [((*part.prefix, "stringUnit"), label, part.text)]

        plural_path = (*part.prefix, "variations", "plural")
        if self._is_left_alone(target, plural_path):
            return []

        existing = self._node_at(target, plural_path)
        existing = existing if isinstance(existing, dict) else None
        needed = required_plural_categories(target_locale) | ({"zero"} if "zero" in part.texts else set())
        fallback = part.texts.get("other") or next(iter(part.texts.values()), "")

        items: list[tuple[tuple[str, ...], str, str]] = []
        for category in sorted(needed, key=_CATEGORY_ORDER.index):
            if existing is not None and not self._leaf_needs_translation(existing.get(category)):
                continue

            text = part.texts.get(category) or fallback
            if text.strip():
                items.append(((*plural_path, category, "stringUnit"), f"{label}.{category}".lstrip("."), text))

        return items

    @staticmethod
    def _source_items(part: _PlainPart | _PluralPart) -> list[tuple[tuple[str, ...], str, str]]:
        """The (path, label, source text) triples of `part` as the source has them."""
        label = _label(part.prefix)
        if isinstance(part, _PlainPart):
            return [((*part.prefix, "stringUnit"), label, part.text)] if part.text.strip() else []

        return [
            ((*part.prefix, "variations", "plural", category, "stringUnit"), f"{label}.{category}".lstrip("."), text)
            for category, text in part.texts.items()
            if text.strip()
        ]

    def _build_units(
        self,
        catalog: dict[str, Any],
        source_locale: str,
        excluded_keys: set[str],
        target_locale: str | None = None,
        writes: _Writes | None = None,
        warn: bool = True,
    ) -> list[TranslationUnit]:
        if (target_locale is None) != (writes is None):
            raise ValueError("'target_locale' and 'writes' must be given together")

        strings = catalog.get("strings") or {}

        units: list[TranslationUnit] = []
        for key, entry in strings.items():
            if key in excluded_keys:
                continue

            if not isinstance(entry, dict):
                self._warn(warn, f"Skipping '{key}': the entry is not an object")
                continue

            if entry.get("shouldTranslate") is False or entry.get("extractionState") == "stale":
                continue

            parts = self._source_parts(key, entry, source_locale, warn)
            if parts is None:
                continue

            comment = entry.get("comment")
            for part in parts:
                items = (
                    self._source_items(part)
                    if target_locale is None
                    else self._pending_items(entry, target_locale, part)
                )
                for path, label, text in items:
                    units.append(
                        TranslationUnit(
                            unit_type=TranslationResourceType.XCSTRINGS,
                            key=f"{key}[{label}]" if label else key,
                            source_text=text,
                            context_hint=comment if isinstance(comment, str) else None,
                            write_back=self._write_back_before_clone
                            if writes is None
                            else self._make_write_back(writes, (key, path)),
                        )
                    )

        return units

    @staticmethod
    def _make_write_back(writes: _Writes, write: _Write) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            writes[write] = translated

        return write_back

    @staticmethod
    def _write_back_before_clone(translated: str) -> None:
        raise ValueError("The parsed catalog has no target locale, clone it for a locale first")

    @staticmethod
    def _save_before_clone(destination: Path) -> None:
        raise ValueError("The parsed catalog has no target locale, clone it for a locale first")

    def clone(self, data: ParseResult, target_locale: str | None = None) -> ParseResult:
        if target_locale is None:
            raise ValueError("A string catalog can only be cloned for a target locale")

        catalog: dict[str, Any] = data.document
        source_locale: str = catalog["sourceLanguage"]
        writes: _Writes = {}

        if target_locale.lower() == source_locale.lower():
            self._logger.warning(
                ConsoleFormatter.warning(f"Skipping '{target_locale}': it is the source language of the catalog")
            )
            units: list[TranslationUnit] = []
        else:
            units = self._build_units(catalog, source_locale, data.excluded_keys, target_locale, writes)

        return ParseResult(
            source_path=data.source_path,
            units=units,
            document=catalog,
            save=self._make_save(catalog, target_locale, writes),
            excluded_keys=data.excluded_keys,
        )

    def _make_save(self, catalog: dict[str, Any], target_locale: str, writes: _Writes) -> Callable[[Path], None]:
        def save(destination: Path) -> None:
            with self._SAVE_LOCK:
                # The file may hold locales other runs wrote since it was parsed, so merge into what is on disk.
                current = self._load_catalog(destination) if destination.exists() else deepcopy(catalog)
                if not writes and destination.exists():
                    return

                self._apply_writes(current, target_locale, writes)
                text = self._dump(current, 0) + "\n"

                def write(tmp: Path) -> None:
                    with tmp.open("w", encoding="utf-8", newline="") as handle:
                        handle.write(text)

                atomic_write(destination, write)

        return save

    @classmethod
    def _apply_writes(cls, catalog: dict[str, Any], target_locale: str, writes: _Writes) -> None:
        source_locale = catalog.get("sourceLanguage")
        strings = catalog.get("strings") or {}
        for (key, path), translated in writes.items():
            entry = strings.get(key)
            if not isinstance(entry, dict):
                continue

            localizations = entry.get("localizations")
            if not isinstance(localizations, dict):
                localizations = {}

            target = localizations.get(target_locale)
            if not isinstance(target, dict):
                target = {}

            source = localizations.get(source_locale)
            cls._write_path(target, source if isinstance(source, dict) else {}, path, translated)
            localizations[target_locale] = target
            # Xcode keeps a string's localizations sorted by locale.
            entry["localizations"] = dict(sorted(localizations.items()))

    @staticmethod
    def _write_path(target: dict[str, Any], source: dict[str, Any], path: tuple[str, ...], translated: str) -> None:
        """Set the `stringUnit` at `path` inside `target`, creating the nodes on the way."""
        node = target
        source_node: Any = source
        sorted_nodes: list[dict[str, Any]] = []
        for index, segment in enumerate(path[:-1]):
            # A plain value and variations exclude each other, the variations replace it.
            if segment == "variations":
                node.pop("stringUnit", None)

            source_node = source_node.get(segment) if isinstance(source_node, dict) else None
            child = node.get(segment)
            if not isinstance(child, dict):
                child = {}
                node[segment] = child

                # A new substitution takes the argument fields of the source's one, everything but its variations.
                if path[index - 1] == "substitutions" and isinstance(source_node, dict):
                    child.update(
                        {k: deepcopy(v) for k, v in source_node.items() if k not in ("variations", "stringUnit")}
                    )

            if segment in ("plural", "device"):
                sorted_nodes.append(child)
            node = child

        node["stringUnit"] = {"state": _TRANSLATED, "value": translated}

        # Xcode keeps the categories of a plural group and the devices of a variation sorted by name.
        for group in sorted_nodes:
            ordered = sorted(group.items())
            group.clear()
            group.update(ordered)

    @classmethod
    def _dump(cls, value: Any, level: int) -> str:
        """Serialize like Xcode: 2-space indent, `"key" : value`, `\\/` escapes and `{ }` written as an empty block."""
        pad, inner = _INDENT * level, _INDENT * (level + 1)

        if isinstance(value, dict):
            if not value:
                return "{\n\n" + pad + "}"
            members = [f"{inner}{cls._dump(k, 0)} : {cls._dump(v, level + 1)}" for k, v in value.items()]
            return "{\n" + ",\n".join(members) + "\n" + pad + "}"

        if isinstance(value, list):
            if not value:
                return "[\n\n" + pad + "]"
            return "[\n" + ",\n".join(f"{inner}{cls._dump(v, level + 1)}" for v in value) + "\n" + pad + "]"

        text = json.dumps(value, ensure_ascii=False)
        return text.replace("/", "\\/") if isinstance(value, str) else text
