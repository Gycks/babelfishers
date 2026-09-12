import hashlib
import threading
import time
from pathlib import Path
from sqlite3 import Connection as SQLite3Connection

from sqlalchemy import event, text
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.engine import Engine
from sqlalchemy.pool import ConnectionPoolEntry
from sqlmodel import Field, Session, SQLModel, col, create_engine, delete, func, select, update

from babelfishers.models.translations import StoreStats


class TranslationMemory(SQLModel, table=True):
    key: str = Field(primary_key=True)
    translated: str
    engine: str = Field(index=True)
    created_at: int = Field(index=True)
    last_used: int = Field(index=True)


class TMStore:
    """Translation Memory Store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._engine: Engine = create_engine(
            f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False}
        )
        event.listens_for(self._engine, "connect")(_set_sqlite_pragma)
        SQLModel.metadata.create_all(self._engine)

    def lookup(
        self,
        source_text: str,
        source_locale: str,
        target_locale: str,
    ) -> str | None:
        """Fetches the cached translation for the source text in the specified
        target locale.

        Args:
            source_text: The original source string.
            source_locale: The source locale.
            target_locale: The target locale.

        Returns:
            The cached translated string, or None if not found.
        """

        key = _make_key(source_text, source_locale, target_locale)

        with Session(self._engine) as session:
            statement = select(TranslationMemory.translated).where(TranslationMemory.key == key)
            return session.exec(statement).first()

    def bump_last_used_for_keys(self, keys: list[str]) -> None:
        """Bump last_used for a batch of cache keys in a single write transaction.

        Args:
            keys: Cache keys.
        """

        if not keys:
            return

        now = _now()
        with self._write_lock, Session(self._engine) as session:
            statement = update(TranslationMemory).where(col(TranslationMemory.key).in_(keys)).values(last_used=now)
            session.exec(statement)
            session.commit()

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

        statement = sqlite_upsert(TranslationMemory).values(
            key=key, translated=translated_text, engine=engine, created_at=now, last_used=now
        )
        statement = statement.on_conflict_do_update(
            index_elements=[TranslationMemory.key],
            set_={
                "translated": statement.excluded.translated,
                "engine": statement.excluded.engine,
                "last_used": statement.excluded.last_used,
            },
        )

        with self._write_lock, Session(self._engine) as session:
            session.exec(statement)
            session.commit()

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

        if not entries:
            return

        now = _now()
        rows = [
            {
                "key": _make_key(src, src_locale, tgt_locale),
                "translated": translated,
                "engine": engine,
                "created_at": now,
                "last_used": now,
            }
            for src, src_locale, tgt_locale, translated in entries
        ]

        statement = sqlite_upsert(TranslationMemory).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[TranslationMemory.key],
            set_={
                "translated": statement.excluded.translated,
                "engine": statement.excluded.engine,
                "last_used": statement.excluded.last_used,
            },
        )

        with self._write_lock, Session(self._engine) as session:
            session.exec(statement)
            session.commit()

    def stats(self) -> StoreStats:
        """Return aggregate statistics about the store."""
        with Session(self._engine) as session:
            total, oldest, newest = session.exec(
                select(
                    func.count(),
                    func.min(TranslationMemory.created_at),
                    func.max(TranslationMemory.last_used),
                )
            ).one()
            engine_rows = session.exec(
                select(TranslationMemory.engine, func.count()).group_by(TranslationMemory.engine)
            ).all()

        size_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0

        return StoreStats(
            total_entries=total or 0,
            oldest_entry_ts=oldest,
            newest_used_ts=newest,
            size_bytes=size_bytes,
            by_engine=dict(engine_rows),
        )

    def prune_older_than(self, days: int) -> int:
        """Delete entries not used in the last `days` days.

        Args:
            days: Entries with last_used older than this many days are deleted.

        Returns:
            Number of entries deleted.
        """

        cutoff = _now() - (days * 86_400)
        with self._write_lock, Session(self._engine) as session:
            result = session.exec(delete(TranslationMemory).where(col(TranslationMemory.last_used) < cutoff))
            session.commit()
            return result.rowcount

    def prune_by_engine(self, engine: str) -> int:
        """Delete all entries produced by a specific engine.

        Args:
            engine: Engine name.

        Returns:
            Number of entries deleted.
        """

        with self._write_lock, Session(self._engine) as session:
            result = session.exec(delete(TranslationMemory).where(col(TranslationMemory.engine) == engine))
            session.commit()
            return result.rowcount

    def prune_keep_newest(self, keep: int) -> int:
        """Keep only the `keep` most recently used entries, deleting the rest.

        Args:
            keep: Number of entries to retain, ordered by last_used descending.

        Returns:
            Number of entries deleted.
        """

        with self._write_lock, Session(self._engine) as session:
            total = session.exec(select(func.count()).select_from(TranslationMemory)).one()

            if total <= keep:
                return 0

            keep_keys = select(TranslationMemory.key).order_by(col(TranslationMemory.last_used).desc()).limit(keep)
            result = session.exec(delete(TranslationMemory).where(col(TranslationMemory.key).not_in(keep_keys)))
            session.commit()
            return result.rowcount

    def vacuum(self) -> None:
        """Reclaim disk space after pruning."""
        with self._write_lock, self._engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("VACUUM"))

    def clear(self) -> None:
        """Wipe the entire store."""
        with self._write_lock, Session(self._engine) as session:
            session.exec(delete(TranslationMemory))
            session.commit()

    @staticmethod
    def make_key(source_text: str, source_locale: str, target_locale: str) -> str:
        return _make_key(source_text, source_locale, target_locale)


def _set_sqlite_pragma(dbapi_connection: SQLite3Connection, connection_record: ConnectionPoolEntry) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _make_key(source_text: str, source_locale: str, target_locale: str) -> str:
    raw = f"{source_locale}|{target_locale}|{source_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())
