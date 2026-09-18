from typing import TYPE_CHECKING

import click

from babelfishers.cli import ui
from babelfishers.cli.errors import CliError
from babelfishers.cli.reports import render_memory_stats
from babelfishers.models.engine import Engine


if TYPE_CHECKING:
    from babelfishers.core.tm_store import TMStore


_ENGINES = [engine.value for engine in Engine]


def _open_store() -> "TMStore | None":
    from babelfishers.core.tm_store import TMStore
    from babelfishers.utils.utils import get_translation_store_storage_path

    path = get_translation_store_storage_path()
    if not path.exists():
        click.echo("The translation memory is empty, nothing has been translated yet.")
        return None

    return TMStore(path)


def _entries(count: int) -> str:
    return f"{count:,} {'entry' if count == 1 else 'entries'}"


@click.group(name="memory", help="Inspect and maintain the translation memory.")
def translation_memory() -> None:
    pass


@translation_memory.command(name="stats", help="Show what the translation memory holds.")
def stats() -> None:
    store = _open_store()
    if store is not None:
        render_memory_stats(store.stats())


@translation_memory.command(name="prune", help="Remove entries from the translation memory. Pick one filter.")
@click.option("--older-than", "days", type=click.IntRange(min=0), help="Remove entries not used in this many days.")
@click.option("--engine", type=click.Choice(_ENGINES, case_sensitive=False), help="Remove entries made by this engine.")
@click.option("--keep", type=click.IntRange(min=0), help="Keep only this many of the most recently used entries.")
def prune(days: int | None, engine: str | None, keep: int | None) -> None:
    if sum(option is not None for option in (days, engine, keep)) != 1:
        raise CliError("Pass exactly one of --older-than, --engine or --keep.")

    store = _open_store()
    if store is None:
        return

    if days is not None:
        removed = store.prune_older_than(days)
    elif engine is not None:
        removed = store.prune_by_engine(engine)
    elif keep is not None:
        removed = store.prune_keep_newest(keep)

    store.vacuum()
    ui.success(f"Removed {_entries(removed)}.")


@translation_memory.command(name="clear", help="Remove every entry from the translation memory.")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def clear(yes: bool) -> None:
    store = _open_store()
    if store is None:
        return

    total = store.stats().total_entries
    if total == 0:
        ui.success("Nothing to do here. The translation memory is already empty")
        return

    if not yes:
        click.confirm(f"Remove {_entries(total)} from the translation memory?", abort=True)

    store.clear()
    store.vacuum()
    ui.success(f"Removed {_entries(total)}.")
