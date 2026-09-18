import pytest
from click.testing import CliRunner

from babelfishers.cli.main import cli
from babelfishers.core.tm_store import TMStore
from babelfishers.utils.utils import get_translation_store_storage_path


DAY = 86_400


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def store():
    return TMStore(get_translation_store_storage_path())


def _add(store, monkeypatch, text, engine="deepl", at=0):
    monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: at)
    store.store(text, "en", "fr", f"[fr] {text}", engine)


def _run(*args, input=None):
    return CliRunner().invoke(cli, ["memory", *args], input=input)


class TestMemoryWithoutStore:
    @pytest.mark.parametrize("args", [["stats"], ["prune", "--keep", "1"], ["clear", "--yes"]])
    def test_reports_an_empty_memory_and_does_not_create_the_store(self, args):
        result = _run(*args)

        assert result.exit_code == 0
        assert "translation memory is empty" in result.output
        assert not get_translation_store_storage_path().exists()


class TestMemoryStats:
    def test_shows_totals_dates_and_the_per_engine_breakdown(self, store, monkeypatch):
        _add(store, monkeypatch, "One", engine="deepl", at=0)
        _add(store, monkeypatch, "Two", engine="deepl", at=DAY)
        _add(store, monkeypatch, "Three", engine="azure", at=2 * DAY)

        result = _run("stats")

        assert result.exit_code == 0
        assert "Entries" in result.output and "3" in result.output
        assert "1970-01-01" in result.output
        assert "1970-01-03" in result.output
        assert "azure" in result.output
        assert "deepl" in result.output

    def test_shows_zero_entries_without_an_engine_table_for_a_store_with_no_entries(self, store):
        result = _run("stats")

        assert result.exit_code == 0
        assert "Entries" in result.output
        assert "Engine" not in result.output


class TestMemoryPrune:
    def test_older_than_removes_only_entries_unused_for_that_many_days(self, store, monkeypatch):
        _add(store, monkeypatch, "Old", at=0)
        _add(store, monkeypatch, "Fresh", at=100 * DAY)
        monkeypatch.setattr("babelfishers.core.tm_store._now", lambda: 100 * DAY)

        result = _run("prune", "--older-than", "30")

        assert result.exit_code == 0
        assert "Removed 1 entry." in result.output
        assert store.lookup("Old", "en", "fr") is None
        assert store.lookup("Fresh", "en", "fr") == "[fr] Fresh"

    def test_engine_removes_only_that_engines_entries_case_insensitively(self, store, monkeypatch):
        _add(store, monkeypatch, "A", engine="deepl")
        _add(store, monkeypatch, "B", engine="azure")

        result = _run("prune", "--engine", "DeepL")

        assert result.exit_code == 0
        assert "Removed 1 entry." in result.output
        assert store.lookup("A", "en", "fr") is None
        assert store.lookup("B", "en", "fr") == "[fr] B"

    def test_keep_retains_the_most_recently_used_entries(self, store, monkeypatch):
        for index, text in enumerate(["First", "Second", "Third"]):
            _add(store, monkeypatch, text, at=index)

        result = _run("prune", "--keep", "1")

        assert result.exit_code == 0
        assert "Removed 2 entries." in result.output
        assert store.lookup("Third", "en", "fr") == "[fr] Third"
        assert store.stats().total_entries == 1

    def test_engine_rejects_a_name_that_is_not_a_known_engine(self, store):
        result = _run("prune", "--engine", "nope")

        assert result.exit_code == 2
        assert "nope" in result.output

    @pytest.mark.parametrize("args", [[], ["--keep", "1", "--engine", "deepl"], ["--older-than", "1", "--keep", "1"]])
    def test_requires_exactly_one_filter(self, store, args):
        result = _run("prune", *args)

        assert result.exit_code == 1
        assert "exactly one of" in result.output


class TestMemoryClear:
    def test_yes_flag_wipes_every_entry_without_asking(self, store, monkeypatch):
        _add(store, monkeypatch, "A")
        _add(store, monkeypatch, "B")

        result = _run("clear", "--yes")

        assert result.exit_code == 0
        assert "Removed 2 entries." in result.output
        assert store.stats().total_entries == 0

    def test_confirming_the_prompt_wipes_the_store(self, store, monkeypatch):
        _add(store, monkeypatch, "A")

        result = _run("clear", input="y\n")

        assert result.exit_code == 0
        assert "Remove 1 entry from the translation memory?" in result.output
        assert store.stats().total_entries == 0

    def test_declining_the_prompt_keeps_everything(self, store, monkeypatch):
        _add(store, monkeypatch, "A")

        result = _run("clear", input="n\n")

        assert result.exit_code == 1
        assert store.stats().total_entries == 1
