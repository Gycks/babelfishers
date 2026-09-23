import click

from babelfishers.cli.reports import render_locales


@click.command(name="locales", help="List the supported locale codes.")
@click.option("--search", "-s", "term", help="Only show locales whose code or name contains this text.")
def locales(term: str | None) -> None:
    render_locales(term)
