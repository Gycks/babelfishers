import json

import click

from babelfishers.cli import ui
from babelfishers.cli.param_types import LocaleListType, LocaleType
from babelfishers.models.engine import Engine


_TOTAL_STEPS = 3
_DEFAULT_SOURCE = "en"
_ENGINES = [engine.value for engine in Engine]


def _render_config(source: str, targets: list[str], engine: str) -> str:
    quoted_targets = ", ".join(json.dumps(target) for target in targets)
    lines = [
        "[locale]",
        f"source = {json.dumps(source)}",
        f"targets = [{quoted_targets}]",
        "",
        "[engine]",
        f"provider = {json.dumps(engine)}",
        "",
        "# List the files to translate, grouped by format. Example:",
        "# [resources.json]",
        '# paths = ["locales/[source]/*.json"]',
        "",
    ]
    return "\n".join(lines)


def _without_source(targets: list[str], source: str) -> list[str]:
    remaining = [target for target in targets if target != source]
    if not remaining:
        raise click.BadParameter(
            f"Provide at least one locale other than the source locale '{source}'.", param_hint="--targets"
        )

    return remaining


def _ask_targets(source: str) -> list[str]:
    while True:
        answer = click.prompt(
            ui.step(2, _TOTAL_STEPS, "Target locales") + ui.hint(" (comma-separated, e.g. fr,de)"),
            type=LocaleListType(),
        )
        try:
            return _without_source(answer, source)
        except click.BadParameter as exc:
            ui.error(exc.message)


@click.command(name="init", help="Initialize a new Babel Fishers project.")
@click.option("--source", type=LocaleType(), help="Source locale code.")
@click.option("--targets", type=LocaleListType(), help="Comma-separated target locale codes.")
@click.option(
    "--engine",
    type=click.Choice(_ENGINES, case_sensitive=False),
    help="Default translation engine.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip every confirmation, including the overwrite one.")
@click.option("--force", is_flag=True, help="Overwrite an existing project without asking.")
def initialize(source: str | None, targets: list[str] | None, engine: str | None, yes: bool, force: bool) -> None:
    from babelfishers.utils.utils import atomic_write, get_app_config_storage_path

    config_path = get_app_config_storage_path()
    if config_path.exists() and not (force or yes):
        click.confirm(f"A Babel Fishers project already exists at {ui.path(config_path)}. Overwrite it?", abort=True)

    is_prompting = source is None or targets is None or engine is None

    ui.title("Initializing a new Babel Fishers project")
    click.echo()

    if source is None:
        source = click.prompt(ui.step(1, _TOTAL_STEPS, "Source locale"), type=LocaleType(), default=_DEFAULT_SOURCE)

    targets = _without_source(targets, source) if targets is not None else _ask_targets(source)

    if engine is None:
        engine = click.prompt(
            ui.step(3, _TOTAL_STEPS, "Translation engine"),
            type=click.Choice(_ENGINES, case_sensitive=False),
        )

    content = _render_config(source, targets, engine)

    if is_prompting:
        click.echo()

    ui.heading("Review")
    ui.row("Source locale", source)
    ui.row("Target locales", ", ".join(targets))
    ui.row("Engine", engine)
    ui.row("File", ui.path(config_path))
    click.echo()
    ui.toml_preview(content)
    click.echo()

    if not yes:
        click.confirm(f"Write {config_path.name}?", default=True, abort=True, show_default=True)

    atomic_write(config_path, lambda tmp_path: tmp_path.write_text(content, encoding="utf-8"))

    ui.success(f"Created {config_path}")
    click.echo()
    ui.heading("Next steps")
    click.echo(f"  1. Set the API credentials for {engine} as environment variables.")
    click.echo(f"  2. List the files to translate under [resources.<format>] in {config_path.name}.")
    click.echo(f"  3. Run {click.style('babelfishers translate', bold=True)}.")
