from pathlib import Path

import click

from babelfishers.cli import ui
from babelfishers.core.supported_cultures import SUPPORTED_CULTURES
from babelfishers.models.engine import Engine
from babelfishers.models.plan import LocalePlan
from babelfishers.models.translation_resource import TranslationResourceType


_HEADERS = ["File", "Locale", "Status", "Units", "Cached", "To translate", "Chars", "Engine"]
_NUMERIC_COLUMNS = {3, 4, 5, 6}
_UP_TO_DATE = "up to date"


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _engine_chain(engines: list[Engine]) -> str:
    first, *fallbacks = dict.fromkeys(engines)
    if not fallbacks:
        return first.value

    return f"{first.value} (fallback: {', '.join(engine.value for engine in fallbacks)})"


def _row(plan: LocalePlan) -> list[str]:
    file = _display_path(plan.source_path)
    reason = plan.stale_reason
    if reason is None:
        return [file, plan.locale, _UP_TO_DATE, "-", "-", "-", "-", "-"]

    volume = plan.volume
    counts = ["-"] * 4
    if volume is not None:
        counts = [
            f"{volume.units_total:,}",
            f"{volume.cached_units:,}",
            f"{volume.units_to_translate:,}",
            f"{volume.characters:,}",
        ]

    return [file, plan.locale, reason.value, *counts, plan.engines[0].value]


def render_dry_run(plans: list[LocalePlan]) -> None:
    ui.title("Dry run")
    click.echo(ui.hint("No translation provider is called and no file is written."))
    click.echo()

    if not plans:
        click.echo("No files to translate.")
        return

    ordered = sorted(plans, key=lambda plan: (str(plan.source_path), plan.locale))
    ui.table(
        _HEADERS,
        [_row(plan) for plan in ordered],
        numeric=_NUMERIC_COLUMNS,
        dimmed={index for index, plan in enumerate(ordered) if not plan.is_stale},
    )
    click.echo()

    stale = [plan for plan in ordered if plan.is_stale]
    volumes = [plan.volume for plan in stale if plan.volume is not None]

    ui.heading("Summary")
    ui.row("Locale jobs", f"{len(ordered)} ({len(stale)} to translate, {len(ordered) - len(stale)} up to date)")

    if not stale:
        click.echo()
        ui.success("Everything is up to date. Nothing would be translated.")
        return

    total = sum(volume.units_total for volume in volumes)
    cached = sum(volume.cached_units for volume in volumes)
    to_translate = sum(volume.units_to_translate for volume in volumes)
    characters = sum(volume.characters for volume in volumes)
    chains = "; ".join(dict.fromkeys(_engine_chain(plan.engines) for plan in stale))

    ui.row("Units", f"{total:,} ({cached:,} cached, {to_translate:,} to translate)")
    ui.row("Characters", f"~{characters:,}")
    ui.row("Engines", chains)
    click.echo()
    click.echo(ui.hint("Unit counts are exact. Characters are an estimate, they assume no retry or fallback. "))


def render_formats() -> None:
    ui.title(f"Supported formats ({len(TranslationResourceType)})")
    click.echo()
    ui.grid([(resource_type.value, "") for resource_type in TranslationResourceType])


def render_locales(term: str | None = None) -> None:
    needle = (term or "").strip().lower()
    cultures = sorted(
        (
            culture
            for culture in SUPPORTED_CULTURES.values()
            if needle in culture.code.lower() or needle in culture.name.lower()
        ),
        key=lambda culture: culture.code,
    )

    if not cultures:
        click.echo(f"No locale matches '{term}'. Run {ui.command('babelfishers locales')} to list them all.")
        return

    heading = f"Locales matching '{term}'" if needle else "Supported locales"
    ui.title(f"{heading} ({len(cultures)})")
    click.echo()
    ui.grid([(culture.code, culture.name) for culture in cultures])
