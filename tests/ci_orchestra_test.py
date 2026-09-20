import logging
from pathlib import Path

import pytest

from babelfishers.core.ci_orchestra import CIOrchestra
from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.errors import CIError
from babelfishers.core.ci_runners.runner import CIRunnerFactory
from babelfishers.models.app_config import AppConfig
from babelfishers.models.ci import CIRunConfig
from babelfishers.models.engine import Engine
from babelfishers.models.plan import RunResult


class _Runner:
    def __init__(self, valid=True, context_error=None, skip=None) -> None:
        self._valid = valid
        self._context_error = context_error
        self._skip = skip
        self.published: list[tuple[list[Path], CIRunConfig]] = []

    def validate(self) -> bool:
        return self._valid

    def skip_reason(self, options) -> str | None:
        return self._skip

    def check_context(self, options) -> None:
        if self._context_error:
            raise self._context_error

    def publish(self, paths, options) -> None:
        self.published.append((paths, options))


class _Runtime:
    def __init__(self, result: RunResult) -> None:
        self._result = result
        self.runs = 0

    def orchestrate_translation_workflow(self) -> RunResult:
        self.runs += 1
        return self._result


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _orchestra(monkeypatch, runner, result: RunResult | None = None) -> tuple[CIOrchestra, _Runtime]:
    monkeypatch.setattr(CIRunnerFactory, "create", staticmethod(lambda runner_type: runner))
    config = AppConfig(
        source_locale="en", target_locales=["fr"], resources=[], translation_engine=Engine.DeepL, glossary=None
    )
    orchestra = CIOrchestra(config)
    runtime = _Runtime(result or RunResult())
    orchestra._translation_runtime = runtime
    return orchestra, runtime


_OPTIONS = CIRunConfig(platform=CIRunnerType.GITHUB, pull_request=True)


class TestCIOrchestra:
    def test_translates_then_publishes_the_changed_paths(self, monkeypatch, tmp_path):
        runner = _Runner()
        result = RunResult(translated=[tmp_path / "fr.json"], state=[tmp_path / "run.lock"])
        orchestra, runtime = _orchestra(monkeypatch, runner, result)

        orchestra.run(_OPTIONS)

        assert runtime.runs == 1
        assert runner.published == [(result.paths, _OPTIONS)]

    def test_rejects_options_that_do_not_fit_the_run_before_anything_is_translated(self, monkeypatch):
        runner = _Runner(context_error=CIError("duplicate"))
        orchestra, runtime = _orchestra(monkeypatch, runner)

        with pytest.raises(CIError, match="duplicate"):
            orchestra.run(_OPTIONS)

        assert runtime.runs == 0

    def test_does_nothing_on_the_wrong_platform(self, monkeypatch):
        runner = _Runner(valid=False)
        orchestra, runtime = _orchestra(monkeypatch, runner)

        orchestra.run(_OPTIONS)

        assert runtime.runs == 0
        assert runner.published == []

    def test_publishes_nothing_when_the_run_changed_nothing(self, monkeypatch):
        runner = _Runner()
        orchestra, runtime = _orchestra(monkeypatch, runner, RunResult())

        orchestra.run(_OPTIONS)

        assert runtime.runs == 1
        assert runner.published == []

    def test_skips_without_translating_or_publishing_when_the_runner_gives_a_reason(self, monkeypatch, caplog):
        runner = _Runner(skip="The latest commit was made by Babel Fishers")
        orchestra, runtime = _orchestra(monkeypatch, runner)

        with caplog.at_level(logging.INFO):
            orchestra.run(_OPTIONS)

        assert runtime.runs == 0
        assert runner.published == []
        assert "made by Babel Fishers" in caplog.text

    def test_decides_to_skip_before_checking_that_the_options_fit_the_run(self, monkeypatch):
        runner = _Runner(skip="fork", context_error=CIError("would fail"))
        orchestra, runtime = _orchestra(monkeypatch, runner)

        orchestra.run(_OPTIONS)

        assert runtime.runs == 0
