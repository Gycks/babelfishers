import pytest
from click.testing import CliRunner

from babelfishers.cli.main import cli
from babelfishers.utils.utils import get_run_lock_storage_path


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _run(*args):
    return CliRunner().invoke(cli, ["run_lock", *args])


class TestRunLockPrune:
    def test_deletes_the_run_lock_file(self, project):
        get_run_lock_storage_path().parent.mkdir(exist_ok=True)
        get_run_lock_storage_path().write_text("{}")

        result = _run("prune")

        assert result.exit_code == 0
        assert "Removed the run lock." in result.output
        assert not get_run_lock_storage_path().exists()

    def test_says_so_when_there_is_no_run_lock(self, project):
        result = _run("prune")

        assert result.exit_code == 0
        assert "no run lock to remove" in result.output


class TestRunLockRefresh:
    def test_records_existing_targets_and_reports_the_ones_still_missing(self, project):
        (project / "locales/fr").mkdir()
        (project / "locales/fr/messages.json").write_text("{}")

        result = _run("refresh")

        assert result.exit_code == 0
        assert "Recorded 1 file/locale pair as up to date." in result.output
        assert "Skipped 1 with no target file yet" in result.output
        assert get_run_lock_storage_path().exists()

    def test_omits_the_skipped_note_when_every_target_exists(self, project):
        for locale in ("fr", "de"):
            (project / f"locales/{locale}").mkdir()
            (project / f"locales/{locale}/messages.json").write_text("{}")

        result = _run("refresh")

        assert "Recorded 2 file/locale pairs as up to date." in result.output
        assert "Skipped" not in result.output

    def test_fails_with_a_message_pointing_to_init_outside_a_project(self):
        result = _run("refresh")

        assert result.exit_code == 1
        assert "babelfishers init" in result.output
