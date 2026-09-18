import hashlib
import json
import logging
import threading
from collections.abc import Collection
from pathlib import Path
from typing import Any

from babelfishers.models.app_config import AppConfig
from babelfishers.models.run_lock import RunLockEntry, StaleReason
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import atomic_write, get_run_lock_storage_path


_FORMAT_VERSION = 1


class RunLockStore:
    """
    Tracks, in a single file, the content hash of every file (source and
    target) touched by the last successful run, keyed by path then locale.
    """

    def __init__(self, destination: Path | None = None) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._destination = destination or get_run_lock_storage_path()
        self._write_lock = threading.Lock()
        self._entries: dict[str, dict[str, RunLockEntry]] = self._load()

    def _load(self) -> dict[str, dict[str, RunLockEntry]]:
        if not self._destination.exists():
            return {}

        raw: dict[str, Any] = json.loads(self._destination.read_text(encoding="utf-8"))
        return {
            path: {locale: RunLockEntry.model_validate(entry) for locale, entry in locales.items()}
            for path, locales in raw.get("entries", {}).items()
        }

    def _save(self) -> None:
        payload = {
            "version": _FORMAT_VERSION,
            "entries": {
                path: {locale: entry.model_dump() for locale, entry in locales.items()}
                for path, locales in self._entries.items()
            },
        }

        def _write(tmp_path: Path) -> None:
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        atomic_write(self._destination, _write)

    def lookup(self, path: str, locale: str) -> RunLockEntry | None:
        return self._entries.get(path, {}).get(locale)

    def stale_reason(
        self, path: str, locale: str, content_hash: str, config_fingerprint: str, destination_path: Path
    ) -> StaleReason | None:
        entry = self.lookup(path, locale)
        if entry is None:
            return StaleReason.NEW

        if not destination_path.exists():
            return StaleReason.TARGET_MISSING

        if entry.content_hash != content_hash:
            return StaleReason.CONTENT_CHANGED

        if entry.config_fingerprint != config_fingerprint:
            return StaleReason.CONFIG_CHANGED

        return None

    def is_stale(
        self, path: str, locale: str, content_hash: str, config_fingerprint: str, destination_path: Path
    ) -> bool:
        return self.stale_reason(path, locale, content_hash, config_fingerprint, destination_path) is not None

    def create(self, entries: list[RunLockEntry]) -> None:
        """Merge `entries` into the store and persist once, regardless of how many are given."""
        if not entries:
            return

        with self._write_lock:
            for entry in entries:
                self._entries.setdefault(entry.path, {})[entry.locale] = entry
            self._logger.info(ConsoleFormatter.info(f"Saving run lock file: {self._destination}"))
            self._save()

    def replace(self, entries: list[RunLockEntry]) -> None:
        """Rebuild the store from `entries` alone, dropping everything recorded before."""
        with self._write_lock:
            self._entries = {}
            for entry in entries:
                self._entries.setdefault(entry.path, {})[entry.locale] = entry
            self._logger.info(ConsoleFormatter.info(f"Saving run lock file: {self._destination}"))
            self._save()

    def remove_orphans(self, live: Collection[tuple[str, str]]) -> int:
        """Drop every entry whose (path, locale) is not in collection. Returns how many were dropped."""
        with self._write_lock:
            kept = {
                path: {locale: entry for locale, entry in locales.items() if (path, locale) in live}
                for path, locales in self._entries.items()
            }
            kept = {path: locales for path, locales in kept.items() if locales}
            removed = sum(len(locales) for locales in self._entries.values()) - sum(
                len(locales) for locales in kept.values()
            )
            if removed == 0:
                return 0

            self._entries = kept
            self._logger.info(ConsoleFormatter.info(f"Removing {removed} orphaned run lock entries"))
            self._save()
            return removed

    def prune(self) -> bool:
        """Delete the run lock file. Returns False when there was nothing to delete."""
        if not self._destination.exists():
            return False

        self._destination.unlink()
        self._entries = {}
        return True


def compute_config_fingerprint(config: AppConfig) -> str:
    """Fingerprints the parts of the config that change what a translated
    output should look like for a given locale: engine and glossary content.
    Distinct from a file's content hash, so a config-only change (e.g.
    switching engines) still invalidates an entry even when the source file
    itself hasn't changed."""

    parts = [
        config.translation_engine.value,
        config.glossary.model_dump_json() if config.glossary else "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
