import hashlib
import json
import logging
import threading
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import register
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write, hash_file_contents


_INDENT = "  "
_TRANSLATED = "translated"


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

    def _source_text(self, key: str, entry: dict[str, Any], source_locale: str, warn: bool = True) -> str | None:
        """The text to translate for one string, or None when it has nothing to translate yet."""
        localizations = entry.get("localizations")
        source = localizations.get(source_locale) if isinstance(localizations, dict) else None

        # Without a source localization, the key is the source text.
        if source is None:
            return key

        if not isinstance(source, dict) or "stringUnit" not in source:
            if warn:
                self._logger.warning(
                    ConsoleFormatter.warning(
                        f"Skipping '{key}': plural, device and substitution strings aren't supported yet"
                    )
                )
            return None

        value = source["stringUnit"].get("value") if isinstance(source["stringUnit"], dict) else None
        if not isinstance(value, str):
            if warn:
                self._logger.warning(ConsoleFormatter.warning(f"Skipping '{key}': its source value is not text"))
            return None

        return value

    @staticmethod
    def _needs_translation(entry: dict[str, Any], target_locale: str) -> bool:
        """Whether the string still lacks a usable target: absent, empty, new or flagged for review."""
        localizations = entry.get("localizations")
        target = localizations.get(target_locale) if isinstance(localizations, dict) else None
        if not isinstance(target, dict):
            return True

        # A target the translator made vary by plural, device or substitution is left alone.
        if "variations" in target:
            return False

        string_unit = target.get("stringUnit")
        if not isinstance(string_unit, dict):
            return True

        value = string_unit.get("value")
        return not (string_unit.get("state") == _TRANSLATED and isinstance(value, str) and value.strip())

    def _build_units(
        self,
        catalog: dict[str, Any],
        source_locale: str,
        excluded_keys: set[str],
        target_locale: str | None = None,
        writes: dict[str, str] | None = None,
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
                if warn:
                    self._logger.warning(ConsoleFormatter.warning(f"Skipping '{key}': the entry is not an object"))
                continue

            if entry.get("shouldTranslate") is False or entry.get("extractionState") == "stale":
                continue

            if target_locale is not None and not self._needs_translation(entry, target_locale):
                continue

            text = self._source_text(key, entry, source_locale, warn)
            if text is None or not text.strip():
                continue

            comment = entry.get("comment")
            units.append(
                TranslationUnit(
                    unit_type=TranslationResourceType.XCSTRINGS,
                    key=key,
                    source_text=text,
                    context_hint=comment if isinstance(comment, str) else None,
                    write_back=self._write_back_before_clone if writes is None else self._make_write_back(writes, key),
                )
            )

        return units

    @staticmethod
    def _make_write_back(writes: dict[str, str], key: str) -> Callable[[str], None]:
        def write_back(translated: str) -> None:
            writes[key] = translated

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
        writes: dict[str, str] = {}

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

    def _make_save(self, catalog: dict[str, Any], target_locale: str, writes: dict[str, str]) -> Callable[[Path], None]:
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

    @staticmethod
    def _apply_writes(catalog: dict[str, Any], target_locale: str, writes: dict[str, str]) -> None:
        strings = catalog.get("strings") or {}
        for key, translated in writes.items():
            entry = strings.get(key)
            if not isinstance(entry, dict):
                continue

            localizations = entry.get("localizations")
            if not isinstance(localizations, dict):
                localizations = {}

            target = localizations.get(target_locale)
            if not isinstance(target, dict):
                target = {}

            target["stringUnit"] = {"state": _TRANSLATED, "value": translated}
            localizations[target_locale] = target
            entry["localizations"] = dict(sorted(localizations.items()))

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
