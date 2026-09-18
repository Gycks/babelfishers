import click

from babelfishers.cli.reports import render_formats


@click.command(name="formats", help="List the supported file formats.")
def formats() -> None:
    render_formats()
