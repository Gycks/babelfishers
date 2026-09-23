from typing import IO, Any

import click

from babelfishers.cli import ui


class CliError(click.ClickException):
    def show(self, file: IO[Any] | None = None) -> None:
        click.echo(ui.format_error(self.format_message()), file=file, err=True, color=ui.color_override())
