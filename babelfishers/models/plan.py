from pathlib import Path

from pydantic import BaseModel

from babelfishers.models.engine import Engine
from babelfishers.models.run_lock import StaleReason


class VolumeEstimate(BaseModel):
    units_total: int
    cached_units: int
    units_to_translate: int
    characters: int


class LocalePlan(BaseModel):
    source_path: Path
    locale: str
    destination: Path
    engines: list[Engine]
    stale_reason: StaleReason | None
    volume: VolumeEstimate | None = None

    @property
    def is_stale(self) -> bool:
        return self.stale_reason is not None


class RunResult(BaseModel):
    """What a translation run changed on disk. All paths are absolute."""

    translated: list[Path] = []
    # Target files left with untranslated text, or not written, because a provider failed.
    incomplete: list[Path] = []
    state: list[Path] = []

    @property
    def paths(self) -> list[Path]:
        """The completely translated target files, then the state files. Empty when there is nothing to keep."""
        return [*self.translated, *self.state]

    @property
    def empty(self) -> bool:
        return len(self.paths) == 0
