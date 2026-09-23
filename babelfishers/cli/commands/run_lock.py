import click

from babelfishers.cli import ui
from babelfishers.cli.project import load_app_config


@click.group(name="run_lock", help="Inspect and maintain the record of the last completed run.")
def run_lock() -> None:
    pass


@run_lock.command(name="prune", help="Delete the run lock file.")
def prune() -> None:
    from babelfishers.core.run_lock import RunLockStore

    if RunLockStore().prune():
        ui.success("Removed the run lock.")
    else:
        click.echo("There is no run lock to remove.")


@run_lock.command(
    name="refresh",
    help="Rebuild the run lock from the config, the sources and the target files on disk.",
)
def refresh() -> None:
    from babelfishers.core.runtime import Runtime

    recorded, skipped = Runtime(load_app_config()).refresh_run_lock()

    ui.success(f"Recorded {recorded:,} file/locale {'pair' if recorded == 1 else 'pairs'} as up to date.")
    if skipped:
        click.echo(ui.hint(f"Skipped {skipped:,} with no target file yet, translate will create them."))
