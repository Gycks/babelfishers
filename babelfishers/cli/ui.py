import math
import os
import shutil
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


def accent(text: str) -> str:
    return click.style(text, fg="blue", bold=True)


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


def table(
    headers: list[str],
    rows: list[list[str]],
    numeric: set[int] | None = None,
    dimmed: set[int] | None = None,
) -> None:
    numeric = numeric or set()
    dimmed = dimmed or set()
    widths = [max([len(header)] + [len(row[index]) for row in rows]) for index, header in enumerate(headers)]

    def render(cells: list[str]) -> str:
        padded = [
            cell.rjust(widths[index]) if index in numeric else cell.ljust(widths[index])
            for index, cell in enumerate(cells)
        ]
        return "  ".join(padded).rstrip()

    click.echo(f"  {click.style(render(headers), bold=True)}")
    for index, row in enumerate(rows):
        line = render(row)
        click.echo(f"  {hint(line) if index in dimmed else line}")


def grid(items: list[tuple[str, str]], gap: int = 3) -> None:
    """Print (key, label) pairs in as many columns as fit the terminal, filled top to bottom like `ls`."""
    if not items:
        return

    key_width = max(len(key) for key, _ in items)
    label_width = max(len(label) for _, label in items)
    available = shutil.get_terminal_size(fallback=(80, 24)).columns - 2
    columns = min(len(items), max(1, (available + gap) // (key_width + 2 + label_width + gap)))
    rows = math.ceil(len(items) / columns)

    for row_index in range(rows):
        cells = []
        for column_index in range(columns):
            item_index = column_index * rows + row_index
            if item_index >= len(items):
                break

            key, label = items[item_index]
            is_last_in_row = column_index == columns - 1 or item_index + rows >= len(items)
            padded_key = key if is_last_in_row and not label else key.ljust(key_width)
            cells.append(f"{accent(padded_key)}  {label.ljust(label_width)}")

        click.echo(f"  {(' ' * gap).join(cells)}".rstrip())


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
