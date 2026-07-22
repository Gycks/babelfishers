import hashlib
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from babelfishers.models.translations import StoreStats


_CREATION_QUERY = """
CREATE TABLE IF NOT EXISTS translation_memory (
    key        TEXT    PRIMARY KEY,
    translated TEXT    NOT NULL,
    engine     TEXT    NOT NULL,
    created_at INTEGER NOT NULL,
    last_used  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_last_used  ON translation_memory (last_used);
CREATE INDEX IF NOT EXISTS idx_engine     ON translation_memory (engine);
CREATE INDEX IF NOT EXISTS idx_created_at ON translation_memory (created_at);
"""


class TMStore:
    """Translation Memory Store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._bootstrap()

    def lookup(
        self,
        source_text: str,
        source_locale: str,
        target_locale: str,
    ) -> str | None:
        """Fetches the cached translation for the source text in the specified
        target locale.

        Updates last_used on every hit so that prune_keep_newest() reflects
        actual recency of use.

        Args:
            source_text: The original source string.
            source_locale: The source locale.
            target_locale: The target locale.

        Returns:
            The cached translated string, or None if not found.
        """

        key = _make_key(source_text, source_locale, target_locale)
        now = _now()

        with self._conn() as conn:
            row = conn.execute(
                "SELECT translated FROM translation_memory WHERE key = ?",
                (key,),
            ).fetchone()

            if row is None:
                return None

            conn.execute(
                "UPDATE translation_memory SET last_used = ? WHERE key = ?",
                (now, key),
            )
            return cast(str, row[0])

    def store(
        self,
        source_text: str,
        source_locale: str,
        target_locale: str,
        translated_text: str,
        engine: str,
    ) -> None:
        """Upsert a single translation.

        On conflict, updates translated, engine, and last_used but
        preserves the original created_at so age-based pruning stays accurate.

        Args:
            source_text: The original source string.
            source_locale: The source locale.
            target_locale: The target locale.
            translated_text: The translated string to cache.
            engine: Name of the engine that produced the translation (metadata only).
        """

        key = _make_key(source_text, source_locale, target_locale)
        now = _now()

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO translation_memory (key, translated, engine, created_at, last_used)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    translated = excluded.translated,
                    engine     = excluded.engine,
                    last_used  = excluded.last_used
                """,
                (key, translated_text, engine, now, now),
            )

    def store_batch(
        self,
        entries: list[tuple[str, str, str, str]],
        engine: str,
    ) -> None:
        """Upsert multiple translations in a single transaction.

        On conflict, updates translated, engine, and last_used but
        preserves the original created_at.

        Args:
            entries: List of (source_text, source_locale, target_locale, translated_text) tuples.
            engine: Name of the engine that produced all entries in this batch.
        """

        now = _now()
        rows = [
            (_make_key(src, src_locale, tgt_locale), translated, engine, now, now)
            for src, src_locale, tgt_locale, translated in entries
        ]
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO translation_memory (key, translated, engine, created_at, last_used)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    translated = excluded.translated,
                    engine     = excluded.engine,
                    last_used  = excluded.last_used
                """,
                rows,
            )

    def stats(self) -> StoreStats:
        """Return aggregate statistics about the store."""
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*), MIN(created_at), MAX(last_used) FROM translation_memory").fetchone()
            engine_rows = conn.execute("SELECT engine, COUNT(*) FROM translation_memory GROUP BY engine").fetchall()

        size_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0

        return StoreStats(
            total_entries=row[0] or 0,
            oldest_entry_ts=row[1],
            newest_used_ts=row[2],
            size_bytes=size_bytes,
            by_engine={r[0]: r[1] for r in engine_rows},
        )

    def prune_older_than(self, days: int) -> int:
        """Delete entries not used in the last `days` days.

        Args:
            days: Entries with last_used older than this many days are deleted.

        Returns:
            Number of entries deleted.
        """

        cutoff = _now() - (days * 86_400)
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM translation_memory WHERE last_used < ?",
                (cutoff,),
            )
            return cursor.rowcount

    def prune_by_engine(self, engine: str) -> int:
        """Delete all entries produced by a specific engine.

        Args:
            engine: Engine name.

        Returns:
            Number of entries deleted.
        """

        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM translation_memory WHERE engine = ?",
                (engine,),
            )
            return cursor.rowcount

    def prune_keep_newest(self, keep: int) -> int:
        """Keep only the `keep` most recently used entries, deleting the rest.

        Args:
            keep: Number of entries to retain, ordered by last_used descending.

        Returns:
            Number of entries deleted.
        """

        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]

            if total <= keep:
                return 0

            cursor = conn.execute(
                """
                DELETE FROM translation_memory
                WHERE key NOT IN (
                    SELECT key FROM translation_memory
                    ORDER BY last_used DESC
                    LIMIT ?
                )
                """,
                (keep,),
            )
            return cursor.rowcount

    def vacuum(self) -> None:
        """Reclaim disk space after pruning."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()

    def clear(self) -> None:
        """Wipe the entire store."""
        with self._conn() as conn:
            conn.execute("DELETE FROM translation_memory")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _bootstrap(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_CREATION_QUERY)
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _make_key(source_text: str, source_locale: str, target_locale: str) -> str:
    raw = f"{source_locale}|{target_locale}|{source_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())
