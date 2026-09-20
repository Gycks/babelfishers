import pytest
from click.testing import CliRunner

from babelfishers.cli.main import cli
from babelfishers.core.ci_orchestra import CIOrchestra
from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.models.ci import CIRunConfig


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def received(project, monkeypatch) -> list[CIRunConfig]:
    options: list[CIRunConfig] = []
    monkeypatch.setattr(CIOrchestra, "run", lambda self, given: options.append(given))
    return options


def _ci(*args):
    return CliRunner().invoke(cli, ["ci", *args])


class TestCiCommand:
    @pytest.mark.parametrize("name", ["github", "GitLab", "BITBUCKET"])
    def test_turns_the_platform_argument_into_the_matching_runner_type(self, received, name):
        result = _ci(name)

        assert result.exit_code == 0
        assert received[0].platform == CIRunnerType(name.lower())

    def test_rejects_an_unknown_platform(self, received):
        result = _ci("jenkins")

        assert result.exit_code == 2
        assert "jenkins" in result.output
        assert received == []

    def test_requires_a_platform(self, received):
        assert _ci().exit_code == 2

    def test_updates_the_current_pull_request_unless_told_to_open_a_new_one(self, received):
        _ci("github")
        _ci("github", "--pull-request")

        assert [options.pull_request for options in received] == [False, True]

    def test_passes_the_given_texts_on(self, received):
        _ci(
            "github",
            "--pull-request",
            "--pull-request-title",
            "Translations",
            "--pull-request-body",
            "Please review",
            "--commit-message",
            "feat: translate",
        )

        options = received[0]
        assert (options.pull_request_title, options.pull_request_body, options.commit_message) == (
            "Translations",
            "Please review",
            "feat: translate",
        )

    def test_keeps_the_defaults_for_the_texts_that_are_not_given(self, received):
        _ci("github")

        assert received[0] == CIRunConfig(platform=CIRunnerType.GITHUB, pull_request=False)

    def test_fails_with_a_message_pointing_to_init_outside_a_project(self, tmp_path):
        result = _ci("github")

        assert result.exit_code == 1
        assert "babelfishers init" in result.output
