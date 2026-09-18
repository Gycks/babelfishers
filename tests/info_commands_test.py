import re

import pytest
from click.testing import CliRunner

from babelfishers.cli import ui
from babelfishers.cli.main import cli
from babelfishers.core.supported_cultures import SUPPORTED_CULTURES
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture(autouse=True)
def fixed_terminal_width(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")


class TestFormatsCommand:
    def test_formats_lists_every_resource_type_key(self):
        result = CliRunner().invoke(cli, ["formats"])

        assert result.exit_code == 0
        for resource_type in TranslationResourceType:
            assert re.search(rf"\b{re.escape(resource_type.value)}\b", result.output), resource_type.value


class TestLocalesCommand:
    def test_locales_lists_every_supported_code_with_its_name(self):
        result = CliRunner().invoke(cli, ["locales"])

        assert result.exit_code == 0
        assert f"Supported locales ({len(SUPPORTED_CULTURES)})" in result.output
        for culture in SUPPORTED_CULTURES.values():
            assert re.search(rf"\b{culture.code}  {re.escape(culture.name)}", result.output), culture.code

    def test_search_matches_the_name_case_insensitively(self):
        result = CliRunner().invoke(cli, ["locales", "--search", "GERMAN"])

        assert "Locales matching 'GERMAN' (1)" in result.output
        assert "German" in result.output
        assert "French" not in result.output

    def test_search_matches_the_code(self):
        result = CliRunner().invoke(cli, ["locales", "-s", "fr"])

        assert "French" in result.output
        assert "German" not in result.output

    def test_search_with_no_match_says_so_and_still_succeeds(self):
        result = CliRunner().invoke(cli, ["locales", "--search", "zzz"])

        assert result.exit_code == 0
        assert "No locale matches 'zzz'" in result.output

    def test_blank_search_lists_everything(self):
        result = CliRunner().invoke(cli, ["locales", "--search", "  "])

        assert f"Supported locales ({len(SUPPORTED_CULTURES)})" in result.output


class TestGrid:
    def test_grid_fills_top_to_bottom_in_as_many_columns_as_fit(self, monkeypatch, capsys):
        monkeypatch.setenv("COLUMNS", "21")

        ui.grid([("a", "One"), ("b", "Two"), ("c", "Three"), ("d", "Four")])

        assert capsys.readouterr().out.splitlines() == ["  a  One     c  Three", "  b  Two     d  Four"]

    def test_grid_falls_back_to_a_single_column_on_a_very_narrow_terminal(self, monkeypatch, capsys):
        monkeypatch.setenv("COLUMNS", "5")

        ui.grid([("a", "One"), ("b", "Two")])

        assert capsys.readouterr().out.splitlines() == ["  a  One", "  b  Two"]

    def test_grid_prints_nothing_for_no_items(self, capsys):
        ui.grid([])

        assert capsys.readouterr().out == ""
