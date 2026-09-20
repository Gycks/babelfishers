import logging

import pytest

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.bitbucket import BitbucketRunner
from babelfishers.core.ci_runners.github import GithubRunner
from babelfishers.core.ci_runners.gitlab import GitlabRunner
from babelfishers.core.ci_runners.runner import CIRunnerFactory


RUNNERS = [
    (CIRunnerType.GITHUB, GithubRunner, "GitHub Actions"),
    (CIRunnerType.GITLAB, GitlabRunner, "GitLab CI/CD"),
    (CIRunnerType.BITBUCKET, BitbucketRunner, "Bitbucket Pipelines"),
]


@pytest.fixture(params=RUNNERS, ids=[runner_type.value for runner_type, _, _ in RUNNERS])
def runner(request, monkeypatch):
    runner_type, cls, name = request.param
    instance = CIRunnerFactory.create(runner_type)
    assert isinstance(instance, cls)
    assert instance.name == name

    for variable in (*instance.required_env, instance.token_env):
        monkeypatch.setenv(variable, "value")
    return instance


class TestRunnerValidate:
    def test_is_true_when_every_required_variable_and_the_token_are_set(self, runner, caplog):
        with caplog.at_level(logging.WARNING):
            assert runner.validate() is True

        assert caplog.records == []

    def test_is_false_and_names_the_variable_when_one_is_missing(self, runner, monkeypatch, caplog):
        missing = runner.required_env[-1]
        monkeypatch.delenv(missing)

        with caplog.at_level(logging.WARNING):
            assert runner.validate() is False

        assert [missing in record.message for record in caplog.records] == [True]
        assert runner.name in caplog.records[0].message

    def test_treats_an_empty_variable_as_missing(self, runner, monkeypatch):
        monkeypatch.setenv(runner.required_env[0], "")

        assert runner.validate() is False

    def test_logs_every_missing_variable_not_just_the_first(self, runner, monkeypatch, caplog):
        for variable in runner.required_env:
            monkeypatch.delenv(variable)

        with caplog.at_level(logging.WARNING):
            assert runner.validate() is False

        logged = " ".join(record.message for record in caplog.records)
        assert all(variable in logged for variable in runner.required_env)

    def test_is_false_and_explains_what_to_pass_when_the_token_is_missing(self, runner, monkeypatch, caplog):
        monkeypatch.delenv(runner.token_env)

        with caplog.at_level(logging.WARNING):
            assert runner.validate() is False

        assert runner.token_env in caplog.records[0].message
        assert runner.token_hint in caplog.records[0].message

    def test_treats_an_empty_token_as_missing(self, runner, monkeypatch):
        monkeypatch.setenv(runner.token_env, "")

        assert runner.validate() is False

    def test_reports_only_the_wrong_platform_when_both_the_platform_and_the_token_are_missing(
        self, runner, monkeypatch, caplog
    ):
        monkeypatch.delenv(runner.token_env)
        monkeypatch.delenv(runner.required_env[0])

        with caplog.at_level(logging.WARNING):
            assert runner.validate() is False

        assert runner.token_env not in " ".join(record.message for record in caplog.records)


class TestRunnerToken:
    def test_is_never_the_default_token_the_platform_hands_to_the_job(self, runner):
        assert runner.token_env.startswith("BF_")
        assert runner.token_env not in ("GITHUB_TOKEN", "CI_JOB_TOKEN")

    def test_the_hint_says_why_the_default_token_is_not_used(self, runner):
        assert "token" in runner.token_hint.lower()
