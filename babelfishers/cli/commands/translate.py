import click

from babelfishers.cli.errors import CliError
from babelfishers.cli.project import load_app_config
from babelfishers.cli.reports import render_dry_run


@click.command(name="translate", help="Translate the project files.")
@click.option("--dry-run", is_flag=True, help="Show what would be translated without making changes.")
def translate(dry_run: bool) -> None:
    from babelfishers.core.runtime import Runtime

    runner = Runtime(load_app_config())

    if dry_run:
        render_dry_run(runner.plan())
        return

    result = runner.orchestrate_translation_workflow()
    if result.incomplete:
        files = ", ".join(str(path) for path in result.incomplete)
        raise CliError(
            f"A provider failed on {files}. What was translated is written and kept in the translation memory, "
            "and the next run translates only what is missing."
        )
