import os
from pathlib import Path

import click


def color_override() -> bool | None:
    return False if os.environ.get("NO_COLOR") else None


def title(text: str) -> None:
    click.secho(text, bold=True)


def heading(text: str) -> None:
    click.secho(text, bold=True, underline=True)


def step(index: int, total: int, label: str) -> str:
    return f"{click.style(f'[{index}/{total}]', fg='blue', bold=True)} {click.style(label, bold=True)}"


def hint(text: str) -> str:
    return click.style(text, dim=True)


def command(text: str) -> str:
    return click.style(text, fg="yellow", bold=True)


def path(value: Path | str) -> str:
    return click.style(str(value), underline=True)


def success(text: str) -> None:
    click.secho(text, fg="green", bold=True)


def format_error(message: str) -> str:
    return f"{click.style('Error:', fg='red', bold=True)} {message}"


def error(text: str) -> None:
    click.echo(format_error(text), err=True)


def row(label: str, value: str) -> None:
    click.echo(f"  {hint((label + ' ').ljust(18, '.'))} {value}")


def toml_preview(text: str) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            click.echo()
        elif stripped.startswith("#"):
            click.echo(f"  {click.style(line, dim=True)}")
        elif stripped.startswith("["):
            click.echo(f"  {click.style(line, fg='blue', bold=True)}")
        elif " = " in line:
            key, value = line.split(" = ", 1)
            click.echo(f"  {key} {hint('=')} {click.style(value, fg='green')}")
        else:
            click.echo(f"  {line}")
