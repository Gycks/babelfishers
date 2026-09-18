import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from babelfishers.models.app_config import AppConfig
from babelfishers.models.run_lock import RunLockEntry
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

    def is_stale(
        self, path: str, locale: str, content_hash: str, config_fingerprint: str, destination_path: Path
    ) -> bool:
        """True if `path`/`locale` has never run, last ran against different content or a
        different config, or its destination file is missing (e.g. deleted by hand since
        the last run). Does not compare the destination file's content: an existing
        destination is trusted as-is, so a manual edit to it is never overwritten here."""

        if not destination_path.exists():
            return True

        entry = self.lookup(path, locale)
        if entry is None:
            return True

        return entry.content_hash != content_hash or entry.config_fingerprint != config_fingerprint

    def create(self, entries: list[RunLockEntry]) -> None:
        """Merge `entries` into the store and persist once, regardless of how many are given."""
        if not entries:
            return

        with self._write_lock:
            for entry in entries:
                self._entries.setdefault(entry.path, {})[entry.locale] = entry
            self._save()

    def prune(self) -> None:
        self._logger.info(ConsoleFormatter.info(f"Removing run lock file: {self._destination}"))
        if not self._destination.exists():
            self._logger.warning(ConsoleFormatter.warning(f"Run lock file does not exist: {self._destination}"))
            return

        self._destination.unlink()
        self._entries = {}
        self._logger.info(ConsoleFormatter.info(f"Run lock file removed: {self._destination}"))


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
