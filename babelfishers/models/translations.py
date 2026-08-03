from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from babelfishers.models.translation_resource import TranslationResourceType


class TranslationUnit(BaseModel):
    unit_type: TranslationResourceType
    key: str
    source_text: str
    write_back: Callable[[str], None]
    translated_text: str = ""
    context_hint: str | None = None
    skip_translation: bool = False


class ParseResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    document: Any

    source_path: Path
    units: list[TranslationUnit]
    save: Callable[[Path], None]


class StoreStats(BaseModel):
    total_entries: int
    oldest_entry_ts: int | None
    newest_used_ts: int | None
    size_bytes: int
    by_engine: dict[str, int] = Field(default_factory=dict)

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)
