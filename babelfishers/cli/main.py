import logging
import sys

import click

from babelfishers import APPLICATION_VERSION
from babelfishers.cli import ui
from babelfishers.cli.commands import COMMANDS
from babelfishers.utils.console_formater import ConsoleFormatter


logging.basicConfig(level=logging.INFO, format="%(message)s")
_logger: logging.Logger = logging.getLogger(__name__)

sys.tracebacklimit = 0


@click.group()
@click.version_option(APPLICATION_VERSION)
def cli() -> None:
    """Babel Fishers command line interface."""


for command in COMMANDS:
    cli.add_command(command)


def main() -> None:
    try:
        cli(color=ui.color_override())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        _logger.error(ConsoleFormatter.error(str(exc)))
        sys.exit(1)
