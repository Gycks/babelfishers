import click

from babelfishers.cli import ui
from babelfishers.cli.errors import CliError


@click.command(name="translate", help="Translate the project files.")
@click.option("--dry-run", is_flag=True, help="Show what would be translated without making changes.")
def translate(dry_run: bool) -> None:
    from babelfishers.core.runtime import Runtime
    from babelfishers.models.app_config import AppConfig
    from babelfishers.utils.utils import get_app_config_storage_path

    config_path = get_app_config_storage_path()
    if not config_path.exists():
        raise CliError(
            f"No Babel Fishers project found at {config_path}. "
            f"Run '{ui.command('babelfishers init')}' first."
        )

    app_config = AppConfig.load(config_path)
    runner = Runtime(app_config, dry_run=dry_run)
    runner.orchestrate_translation_workflow()
