import difflib
import re
from typing import Any

import click

from babelfishers.core.supported_cultures import SUPPORTED_CULTURES


def _unknown_locale_message(code: str) -> str:
    close_matches = difflib.get_close_matches(code, SUPPORTED_CULTURES.keys(), n=1)
    if close_matches:
        return f"Unknown locale '{code}'. Did you mean '{close_matches[0]}'?"

    return f"Unknown locale '{code}'. Supported locales: {', '.join(sorted(SUPPORTED_CULTURES))}"


class LocaleType(click.ParamType[str]):
    name = "locale"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> str:
        code = str(value).strip().lower()
        if code not in SUPPORTED_CULTURES:
            self.fail(_unknown_locale_message(code), param, ctx)

        return code


class LocaleListType(click.ParamType[list[str]]):
    name = "locales"

    def __init__(self) -> None:
        self._locale_type = LocaleType()

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> list[str]:
        if isinstance(value, list):
            return value

        parts = [part for part in re.split(r"[,\s]+", str(value)) if part]
        if not parts:
            self.fail("Enter at least one locale code.", param, ctx)

        locales: list[str] = []
        for part in parts:
            code = self._locale_type.convert(part, param, ctx)
            if code not in locales:
                locales.append(code)

        return locales
