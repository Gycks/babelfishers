import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.errors import CIError
from babelfishers.core.ci_runners.git import Git
from babelfishers.models.ci import CIRunConfig, bot_branch_name, is_bot_branch
from babelfishers.utils.console_formater import ConsoleFormatter
from babelfishers.utils.utils import get_env


_registry: dict[CIRunnerType, type] = {}

BOT_NAME = "Babel Fishers"
BOT_EMAIL = "bot@babelfishers.local"
_REQUEST_TIMEOUT_SECONDS = 30


def register(runner_type: CIRunnerType) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _registry[runner_type] = cls
        return cls

    return decorator


class BaseRunner(ABC):
    def __init__(self) -> None:
        self._logger: logging.Logger = logging.getLogger(__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the CI platform, used in log messages."""

    @property
    @abstractmethod
    def required_env(self) -> tuple[str, ...]:
        """Environment variables the platform sets on every run, whatever the trigger."""

    @property
    @abstractmethod
    def token_env(self) -> str:
        """
        Name of the environment variable the user passes a personal access token in.

        Not the token the platform hands to the job itself: none of them is enough to push commits that start
        the pull request's own checks and to open pull requests, so the user has to provide one.
        """

    @property
    @abstractmethod
    def token_hint(self) -> str:
        """Why the platform's own token is not used, and what kind of token to pass in `token_env` instead."""

    @property
    @abstractmethod
    def current_branch(self) -> str | None:
        """The branch this run belongs to, read from the platform's environment. None when it cannot be told."""

    @property
    @abstractmethod
    def pull_request_branch(self) -> str | None:
        """The branch the current pull request comes from. None when this run does not belong to a pull request."""

    @property
    def is_fork_pull_request(self) -> bool:
        """
        Whether the current pull request comes from a fork. The platform's token cannot push to a fork's branch,
        so these are skipped. False when the platform cannot tell.
        """
        return False

    @abstractmethod
    def find_pull_request(self, branch: str, base: str) -> str | None:
        """The URL of the open pull request from `branch` into `base`, or None when there is none."""

    @abstractmethod
    def create_pull_request(self, branch: str, base: str, title: str, body: str) -> str:
        """Open a pull request from `branch` into `base` and return its URL."""

    def validate(self) -> bool:
        """
        Check that the process really runs on this CI platform.

        Every variable in `required_env` must be set and not empty. On the right platform, the user's token
        in `token_env` must be set too, since the run cannot write anything back without it.

        Returns:
            True when everything is present, False otherwise. Every problem found is logged.
        """
        missing = [variable for variable in self.required_env if not get_env(variable, raise_on_error=False)]
        for variable in missing:
            self._logger.warning(
                ConsoleFormatter.warning(f"Not running on {self.name}: environment variable {variable} is not set")
            )
        if missing:
            return False

        if not get_env(self.token_env, raise_on_error=False):
            self._logger.warning(
                ConsoleFormatter.warning(f"The environment variable {self.token_env} is not set. {self.token_hint}")
            )
            return False

        return True

    def push_remote(self) -> str:
        """Where to push. Platforms whose checkout has no push credentials return an authenticated URL."""
        return "origin"

    def skip_reason(self, options: CIRunConfig) -> str | None:
        """
        Why this run should be skipped without translating anything, or None when it should go ahead.

        A run is skipped when it cannot do its job (a fork's pull request cannot be pushed to) or when it would
        only react to its own work: the latest commit was made by the bot, or the run is on a bot branch. That
        is how the commits the bot pushes stay from starting translations of their own.
        """
        if not options.pull_request and self.is_fork_pull_request:
            return "This pull request comes from a fork, and the token cannot push to a fork"

        branch = self.current_branch
        if branch and is_bot_branch(branch):
            return f"{branch} is a {BOT_NAME} branch"

        if self._git().head_author() == (BOT_NAME, BOT_EMAIL):
            return f"The latest commit was made by {BOT_NAME}"

        return None

    def check_context(self, options: CIRunConfig) -> None:
        """
        Check that `options` fit the run this process is part of, before any translation.

        Opening a new pull request needs a run that is not part of one, so it cannot duplicate it, and a
        known base branch. Updating the current pull request needs a run that is part of one, whose checkout
        is the latest commit of that pull request's branch.

        Raises:
            CIError: The options and the run do not fit.
        """
        if options.pull_request:
            if self.pull_request_branch:
                raise CIError(
                    f"This run belongs to a pull request from {self.pull_request_branch}. Opening a new pull "
                    "request from here would duplicate it. Update the current one instead."
                )
            self._base_branch()
            return

        branch = self._require_pull_request_branch()
        # A pull request run often checks out the merge result. Pushing that would merge the base into the branch.
        git = self._git()
        if git.remote_tip(self.push_remote(), branch) != git.head_commit():
            raise CIError(
                f"The checkout is not the latest commit of {branch}. Check out that branch itself, "
                "not the merge result, and run again."
            )

    def publish(self, paths: list[Path], options: CIRunConfig) -> None:
        """
        Write the changes back to the repository.

        Remarks:
        - `options.pull_request`: the commit goes to the bot branch, which is force-pushed so it always sits
          on the current base, and a pull request from that branch is opened unless one is already open.
        - otherwise: the commit is pushed to the branch of the pull request this run belongs to, which
          updates that pull request.

        Nothing is committed, pushed or opened when the paths hold no change.

        Args:
            paths: The files the run changed.
            options: What to commit, and whether to open a new pull request or update the current one.

        Raises:
            CIError: The options do not fit the run, the checkout is not the latest commit of the pull
                request's branch, a token is missing, or git or the platform's API rejects a step.
        """
        self.check_context(options)
        if not paths:
            self._logger.info(ConsoleFormatter.info("Nothing to commit"))
            return

        if options.pull_request:
            self._publish_new_pull_request(paths, options)
        else:
            self._publish_to_pull_request_branch(paths, options)

    def _git(self) -> Git:
        return Git(secrets=[get_env(self.token_env, raise_on_error=False)])

    def _base_branch(self) -> str:
        base_branch = self.current_branch
        if not base_branch:
            raise CIError(f"Could not tell which branch {self.name} is running on. Run it on a branch, not a tag.")

        return base_branch

    def _require_pull_request_branch(self) -> str:
        branch = self.pull_request_branch
        if not branch:
            raise CIError(
                "This run does not belong to a pull request, so there is nothing to update. "
                "Open a new pull request instead."
            )

        return branch

    def _publish_new_pull_request(self, paths: list[Path], options: CIRunConfig) -> None:
        base = self._base_branch()
        branch = bot_branch_name(base)
        git = self._git()

        git.stage(paths)
        if not git.has_staged_changes():
            self._logger.info(ConsoleFormatter.info("No changes to commit"))
            return

        git.checkout_branch(branch)
        git.commit(options.commit_message, BOT_NAME, BOT_EMAIL)
        git.push(self.push_remote(), f"HEAD:refs/heads/{branch}", force=True)
        self._logger.info(ConsoleFormatter.info(f"Pushed {branch}"))
        self._open_pull_request(options, branch, base)

    def _publish_to_pull_request_branch(self, paths: list[Path], options: CIRunConfig) -> None:
        branch = self._require_pull_request_branch()
        git = self._git()

        git.stage(paths)
        if not git.has_staged_changes():
            self._logger.info(ConsoleFormatter.info("No changes to commit"))
            return

        git.commit(options.commit_message, BOT_NAME, BOT_EMAIL)
        git.push(self.push_remote(), f"HEAD:refs/heads/{branch}")
        self._logger.info(ConsoleFormatter.success(f"Pushed the translations to {branch}"))

    def _open_pull_request(self, options: CIRunConfig, branch: str, base: str) -> None:
        existing = self.find_pull_request(branch, base)
        if existing:
            self._logger.info(ConsoleFormatter.success(f"Updated the open pull request: {existing}"))
            return

        created = self.create_pull_request(
            branch, base, options.pull_request_title or options.commit_message, options.pull_request_body
        )
        self._logger.info(ConsoleFormatter.success(f"Opened a pull request: {created}"))

    def _token(self) -> str:
        token = get_env(self.token_env, raise_on_error=False)
        if not token:
            raise CIError(f"The environment variable {self.token_env} is not set. {self.token_hint}")

        return token

    def _request(self, method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(  # noqa: S310
            url,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                return json.loads(response.read() or "null")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise CIError(f"{self.name} API {method} {url} failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CIError(f"{self.name} API {method} {url} failed: {exc.reason}") from exc


class CIRunnerFactory:
    @staticmethod
    def create(runner_type: CIRunnerType) -> BaseRunner:
        cls = _registry.get(runner_type)
        if cls is None:
            raise ValueError(f"No class registered for {runner_type}")

        runner = cls()
        if not isinstance(runner, BaseRunner):
            raise ValueError(f"Invalid translator: {runner_type}")

        return runner
