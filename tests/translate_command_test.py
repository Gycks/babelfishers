import json

import pytest
from click.testing import CliRunner

from babelfishers.cli.main import cli
from babelfishers.core.translators.registry import translators_registry
from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "locales/en/messages.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"greeting": "Hello"}), encoding="utf-8")
    (tmp_path / "babelfishers.toml").write_text(
        '[locale]\nsource = "en"\ntargets = ["fr", "de"]\n\n'
        '[engine]\nprovider = "deepl"\n\n'
        '[resources.json]\npaths = ["locales/[source]/messages.json"]\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def call_log(monkeypatch):
    calls = []

    class _Translator(Translator):
        def __init__(self) -> None:
            super().__init__(Engine.DeepL)

        def translate(self, data, source, target):
            calls.append(target)
            for unit in data:
                unit.translated_text = f"[{target}] {unit.source_text}"
            return data

    monkeypatch.setitem(translators_registry, Engine.DeepL, _Translator)
    return calls


class TestTranslateDryRun:
    def test_dry_run_prints_the_plan_without_calling_the_provider_or_writing_files(self, project, call_log):
        result = CliRunner().invoke(cli, ["translate", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "locales/en/messages.json" in result.output
        assert "new" in result.output
        assert "Summary" in result.output
        assert call_log == []
        assert not (project / "locales/fr").exists()
        assert not (project / ".babelfishers").exists()

    def test_dry_run_reports_everything_up_to_date_after_a_real_run(self, project, call_log):
        runner = CliRunner()
        assert runner.invoke(cli, ["translate"]).exit_code == 0
        calls_after_real_run = list(call_log)

        result = runner.invoke(cli, ["translate", "--dry-run"])

        assert result.exit_code == 0
        assert "Everything is up to date" in result.output
        assert call_log == calls_after_real_run

    def test_dry_run_reports_a_deleted_target_file(self, project, call_log):
        runner = CliRunner()
        runner.invoke(cli, ["translate"])
        (project / "locales/fr/messages.json").unlink()

        result = runner.invoke(cli, ["translate", "--dry-run"])

        assert "target missing" in result.output
        assert "1 to translate, 1 up to date" in result.output


class TestTranslateWithoutProject:
    def test_translate_fails_with_a_message_pointing_to_init(self, tmp_path):
        result = CliRunner().invoke(cli, ["translate"])

        assert result.exit_code == 1
        assert "No Babel Fishers project found" in result.output
        assert "babelfishers init" in result.output
