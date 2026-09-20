import base64
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.errors import CIError
from babelfishers.core.ci_runners.git import Git
from babelfishers.core.ci_runners.runner import BOT_EMAIL, BOT_NAME, BaseRunner
from babelfishers.models.ci import CIRunConfig


BOT_BRANCH = "babelfishers/translations/main"
DEFAULT_MESSAGE = CIRunConfig(platform=CIRunnerType.GITHUB, pull_request=True).commit_message


def _git(cwd, *args) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class _FakeRunner(BaseRunner):
    def __init__(self, remote, branch="main", pull_request_branch=None, existing_pull_request=None, fork=False) -> None:
        super().__init__()
        self._remote = remote
        self._branch = branch
        self._pull_request_branch = pull_request_branch
        self._fork = fork
        self._existing_pull_request = existing_pull_request
        self.created: list[tuple[str, str, str, str]] = []

    @property
    def name(self) -> str:
        return "Fake CI"

    @property
    def required_env(self) -> tuple[str, ...]:
        return ()

    @property
    def token_env(self) -> str:
        return "FAKE_CI_TOKEN"

    @property
    def token_hint(self) -> str:
        return "Pass a token."

    @property
    def current_branch(self) -> str | None:
        return self._branch

    @property
    def pull_request_branch(self) -> str | None:
        return self._pull_request_branch

    @property
    def is_fork_pull_request(self) -> bool:
        return self._fork

    def push_remote(self) -> str:
        return str(self._remote)

    def find_pull_request(self, branch: str, base: str) -> str | None:
        return self._existing_pull_request

    def create_pull_request(self, branch: str, base: str, title: str, body: str) -> str:
        self.created.append((branch, base, title, body))
        return "https://example.com/pull/1"


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(path))
    return path


@pytest.fixture
def work(tmp_path, remote, monkeypatch):
    path = tmp_path / "work"
    _git(tmp_path, "clone", str(remote), str(path))
    (path / "README.md").write_text("hello\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial")
    _git(path, "push", "origin", "HEAD:refs/heads/main")
    monkeypatch.chdir(path)
    return path


@pytest.fixture
def changed(work):
    path = work / "locales/fr.json"
    path.parent.mkdir()
    path.write_text('{"greeting": "Bonjour"}\n')
    return path


@pytest.fixture
def feature(remote, work):
    """A pull request branch 'feature' with one commit of its own, checked out in the working copy."""
    _git(work, "checkout", "-b", "feature")
    (work / "feature.txt").write_text("feature work\n")
    _git(work, "add", "feature.txt")
    _git(work, "commit", "-m", "feature work")
    _git(work, "push", "origin", "feature")
    return "feature"


def _new_pull_request(**overrides) -> CIRunConfig:
    return CIRunConfig(platform=CIRunnerType.GITHUB, pull_request=True, **overrides)


def _update_pull_request(**overrides) -> CIRunConfig:
    return CIRunConfig(platform=CIRunnerType.GITHUB, pull_request=False, **overrides)


class TestOpenNewPullRequest:
    def test_pushes_the_bot_branch_leaves_the_base_alone_and_opens_a_pull_request(self, remote, changed):
        runner = _FakeRunner(remote)

        runner.publish([changed], _new_pull_request())

        options = _new_pull_request()
        assert _git(remote, "log", "-1", "--format=%s", "main") == "initial"
        assert _git(remote, "log", "-1", "--format=%an|%s", BOT_BRANCH) == f"{BOT_NAME}|{DEFAULT_MESSAGE}"
        assert runner.created == [(BOT_BRANCH, "main", DEFAULT_MESSAGE, options.pull_request_body)]

    def test_uses_the_given_message_title_and_body(self, remote, changed):
        runner = _FakeRunner(remote)

        runner.publish(
            [changed],
            _new_pull_request(
                commit_message="feat: translate", pull_request_title="Translations", pull_request_body="Please review"
            ),
        )

        assert _git(remote, "log", "-1", "--format=%s", BOT_BRANCH) == "feat: translate"
        assert runner.created == [(BOT_BRANCH, "main", "Translations", "Please review")]

    def test_uses_the_commit_message_as_the_title_when_no_title_is_given(self, remote, changed):
        runner = _FakeRunner(remote)

        runner.publish([changed], _new_pull_request(commit_message="feat: translate"))

        assert runner.created[0][2] == "feat: translate"

    def test_targets_the_branch_the_run_is_on(self, remote, changed):
        runner = _FakeRunner(remote, branch="release/1.0")

        runner.publish([changed], _new_pull_request())

        assert runner.created[0][:2] == ("babelfishers/translations/release_2F1.0", "release/1.0")

    def test_opens_no_second_pull_request_when_one_is_already_open(self, remote, changed):
        runner = _FakeRunner(remote, existing_pull_request="https://example.com/pull/7")

        runner.publish([changed], _new_pull_request())

        assert runner.created == []
        assert _git(remote, "rev-parse", "--verify", BOT_BRANCH)

    def test_rebuilds_the_bot_branch_on_the_base_so_it_is_one_commit_ahead(self, remote, work, changed):
        runner = _FakeRunner(remote)
        runner.publish([changed], _new_pull_request())
        _git(work, "checkout", "main")
        changed.parent.mkdir()
        changed.write_text('{"greeting": "Salut"}\n')

        runner.publish([changed], _new_pull_request())

        assert _git(remote, "rev-list", "--count", f"main..{BOT_BRANCH}") == "1"
        assert _git(remote, "show", f"{BOT_BRANCH}:locales/fr.json") == '{"greeting": "Salut"}'

    def test_stages_files_the_project_ignores(self, remote, work, changed):
        (work / ".gitignore").write_text("locales/\n")
        _git(work, "add", ".gitignore")
        _git(work, "commit", "-m", "ignore locales")
        _git(work, "push", "origin", "HEAD:refs/heads/main")

        _FakeRunner(remote).publish([changed], _new_pull_request())

        assert _git(remote, "show", f"{BOT_BRANCH}:locales/fr.json") == '{"greeting": "Bonjour"}'

    def test_does_nothing_when_there_is_nothing_new_to_commit(self, remote, work):
        runner = _FakeRunner(remote)

        runner.publish([work / "README.md"], _new_pull_request())

        assert runner.created == []
        assert _git(work, "branch", "--list", BOT_BRANCH) == ""

    def test_does_nothing_for_an_empty_list_of_paths(self, remote, work):
        runner = _FakeRunner(remote)

        runner.publish([], _new_pull_request())

        assert runner.created == []

    def test_refuses_to_open_a_pull_request_from_a_run_that_belongs_to_one(self, remote, changed):
        runner = _FakeRunner(remote, pull_request_branch="feature")

        with pytest.raises(CIError, match="duplicate"):
            runner.publish([changed], _new_pull_request())

        assert runner.created == []

    def test_fails_when_the_branch_cannot_be_detected(self, remote, changed):
        with pytest.raises(CIError, match="Could not tell"):
            _FakeRunner(remote, branch=None).publish([changed], _new_pull_request())


class TestUpdateCurrentPullRequest:
    def test_commits_onto_the_pull_request_branch_and_touches_nothing_else(self, remote, changed, feature):
        runner = _FakeRunner(remote, pull_request_branch=feature)
        main_before = _git(remote, "rev-parse", "main")

        runner.publish([changed], _update_pull_request())

        assert _git(remote, "log", "-1", "--format=%an|%s", feature) == f"{BOT_NAME}|{DEFAULT_MESSAGE}"
        assert _git(remote, "show", f"{feature}:locales/fr.json") == '{"greeting": "Bonjour"}'
        assert _git(remote, "show", f"{feature}:feature.txt") == "feature work"
        assert _git(remote, "rev-parse", "main") == main_before
        assert _git(remote, "branch", "--list", "babelfishers/*") == ""
        assert runner.created == []

    def test_adds_one_commit_on_top_of_the_branch_without_rewriting_it(self, remote, changed, feature):
        tip_before = _git(remote, "rev-parse", feature)

        _FakeRunner(remote, pull_request_branch=feature).publish([changed], _update_pull_request())

        assert _git(remote, "rev-list", "--count", f"{tip_before}..{feature}") == "1"

    def test_uses_the_given_commit_message(self, remote, changed, feature):
        _FakeRunner(remote, pull_request_branch=feature).publish(
            [changed], _update_pull_request(commit_message="feat: translate")
        )

        assert _git(remote, "log", "-1", "--format=%s", feature) == "feat: translate"

    def test_stages_files_the_project_ignores(self, remote, work, changed, feature):
        (work / ".gitignore").write_text("locales/\n")
        _git(work, "add", ".gitignore")
        _git(work, "commit", "-m", "ignore locales")
        _git(work, "push", "origin", feature)

        _FakeRunner(remote, pull_request_branch=feature).publish([changed], _update_pull_request())

        assert _git(remote, "show", f"{feature}:locales/fr.json") == '{"greeting": "Bonjour"}'

    def test_does_nothing_when_the_files_match_what_is_already_committed(self, remote, work, feature):
        tip_before = _git(remote, "rev-parse", feature)

        _FakeRunner(remote, pull_request_branch=feature).publish([work / "README.md"], _update_pull_request())

        assert _git(remote, "rev-parse", feature) == tip_before

    def test_refuses_a_checkout_that_is_not_the_latest_commit_of_the_pull_request_branch(
        self, remote, work, changed, feature
    ):
        _git(work, "checkout", "main")
        changed.parent.mkdir(exist_ok=True)
        changed.write_text('{"greeting": "Bonjour"}\n')
        tip_before = _git(remote, "rev-parse", feature)

        with pytest.raises(CIError, match="latest commit"):
            _FakeRunner(remote, pull_request_branch=feature).publish([changed], _update_pull_request())

        assert _git(remote, "rev-parse", feature) == tip_before
        assert _git(remote, "log", "-1", "--format=%s", "main") == "initial"

    def test_refuses_a_run_that_does_not_belong_to_a_pull_request_and_never_pushes_to_the_base(self, remote, changed):
        main_before = _git(remote, "rev-parse", "main")

        with pytest.raises(CIError, match="nothing to update"):
            _FakeRunner(remote, pull_request_branch=None).publish([changed], _update_pull_request())

        assert _git(remote, "rev-parse", "main") == main_before


class TestCheckContext:
    def test_accepts_a_new_pull_request_outside_a_pull_request_run(self, remote):
        _FakeRunner(remote).check_context(_new_pull_request())

    def test_accepts_an_update_inside_a_pull_request_run(self, remote, feature):
        _FakeRunner(remote, pull_request_branch=feature).check_context(_update_pull_request())

    def test_rejects_a_new_pull_request_inside_a_pull_request_run(self, remote):
        with pytest.raises(CIError, match="duplicate"):
            _FakeRunner(remote, pull_request_branch="feature").check_context(_new_pull_request())

    def test_rejects_an_update_outside_a_pull_request_run(self, remote):
        with pytest.raises(CIError, match="nothing to update"):
            _FakeRunner(remote).check_context(_update_pull_request())

    def test_rejects_a_new_pull_request_when_the_branch_is_unknown(self, remote):
        with pytest.raises(CIError, match="Could not tell"):
            _FakeRunner(remote, branch=None).check_context(_new_pull_request())

    def test_rejects_an_update_whose_checkout_is_not_the_latest_commit_of_the_pull_request_branch(
        self, remote, work, feature
    ):
        _git(work, "checkout", "main")

        with pytest.raises(CIError, match="latest commit"):
            _FakeRunner(remote, pull_request_branch=feature).check_context(_update_pull_request())


def _commit_as(cwd, name, email, message):
    (cwd / f"{message}.txt").write_text(message)
    _git(cwd, "add", ".")
    _git(cwd, "-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-m", message)


class TestSkipReason:
    def test_goes_ahead_when_a_person_made_the_latest_commit(self, remote, work):
        assert _FakeRunner(remote).skip_reason(_new_pull_request()) is None

    def test_skips_when_the_bot_made_the_latest_commit(self, remote, work):
        _commit_as(work, BOT_NAME, BOT_EMAIL, "translations")

        assert "made by Babel Fishers" in _FakeRunner(remote).skip_reason(_new_pull_request())

    def test_goes_ahead_when_a_person_committed_after_the_bot(self, remote, work):
        _commit_as(work, BOT_NAME, BOT_EMAIL, "translations")
        _commit_as(work, "Dev", "dev@example.com", "new source text")

        assert _FakeRunner(remote).skip_reason(_new_pull_request()) is None

    def test_skips_on_a_bot_branch_even_when_a_person_made_the_latest_commit(self, remote, work):
        runner = _FakeRunner(remote, branch="babelfishers/translations/main")

        assert "Babel Fishers branch" in runner.skip_reason(_new_pull_request())

    def test_skips_a_pull_request_from_a_fork_when_updating(self, remote, work):
        runner = _FakeRunner(remote, pull_request_branch="feature", fork=True)

        assert "fork" in runner.skip_reason(_update_pull_request())

    def test_ignores_the_fork_flag_when_opening_a_new_pull_request(self, remote, work):
        assert _FakeRunner(remote, fork=True).skip_reason(_new_pull_request()) is None


class TestGit:
    def test_errors_hide_the_secrets_they_were_given(self, tmp_path):
        git = Git(cwd=tmp_path, secrets=["s3cret-token"])
        _git(tmp_path, "init")

        with pytest.raises(CIError) as error:
            git.push("/nowhere/s3cret-token.git", "HEAD:refs/heads/main")

        assert "s3cret-token" not in str(error.value)
        assert "***" in str(error.value)

    def test_remote_tip_is_none_for_a_branch_that_does_not_exist(self, remote, work):
        assert Git().remote_tip(str(remote), "missing") is None
        assert Git().remote_tip(str(remote), "main") == Git().head_commit()


class _Recorder(BaseHTTPRequestHandler):
    """Asks for credentials, then rejects the repository, and records what each request carried."""

    seen: list[dict[str, str | None]] = []

    def do_GET(self):  # noqa: N802
        authorization = self.headers.get("Authorization")
        _Recorder.seen.append({"authorization": authorization, "x-foo": self.headers.get("X-Foo")})
        self.send_response(401 if authorization is None else 404)
        if authorization is None:
            self.send_header("WWW-Authenticate", 'Basic realm="git"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def _basic(user_and_password: str) -> str:
    return "Basic " + base64.b64encode(user_and_password.encode()).decode()


@pytest.fixture
def git_server(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    _Recorder.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    repo = tmp_path / "repo"
    _git(tmp_path, "init", str(repo))
    _git(repo, "commit", "--allow-empty", "-m", "initial")
    base = f"http://127.0.0.1:{httpd.server_port}"
    yield repo, base
    httpd.shutdown()
    httpd.server_close()


class TestGitSavedAuthorization:
    """A checkout can save the platform's default token as a header. It must not win over the token in the URL."""

    def _save_header(self, repo, base, header):
        _git(repo, "config", f"http.{base}/.extraheader", header)

    def _credentials_sent(self):
        return {request["authorization"] for request in _Recorder.seen if request["authorization"]}

    def test_a_push_uses_the_credentials_in_the_url_not_a_saved_authorization_header(self, git_server):
        repo, base = git_server
        self._save_header(repo, base, f"AUTHORIZATION: {_basic('x-access-token:default')}")

        with pytest.raises(CIError):
            Git(cwd=repo).push(f"http://x-access-token:pat@{base.removeprefix('http://')}/o/r.git", "HEAD:refs/heads/x")

        assert self._credentials_sent() == {_basic("x-access-token:pat")}

    def test_reading_the_remote_tip_uses_the_credentials_in_the_url_too(self, git_server):
        repo, base = git_server
        self._save_header(repo, base, f"Authorization: {_basic('x-access-token:default')}")

        with pytest.raises(CIError):
            Git(cwd=repo).remote_tip(f"http://x-access-token:pat@{base.removeprefix('http://')}/o/r.git", "main")

        assert self._credentials_sent() == {_basic("x-access-token:pat")}

    def test_a_saved_header_that_is_not_authorization_is_left_alone(self, git_server):
        repo, base = git_server
        self._save_header(repo, base, "X-Foo: bar")

        with pytest.raises(CIError):
            Git(cwd=repo).remote_tip(f"http://x-access-token:pat@{base.removeprefix('http://')}/o/r.git", "main")

        assert {request["x-foo"] for request in _Recorder.seen} == {"bar"}
        assert self._credentials_sent() == {_basic("x-access-token:pat")}

    def test_does_nothing_special_when_nothing_was_saved(self, git_server):
        repo, base = git_server

        with pytest.raises(CIError):
            Git(cwd=repo).remote_tip(f"http://x-access-token:pat@{base.removeprefix('http://')}/o/r.git", "main")

        assert self._credentials_sent() == {_basic("x-access-token:pat")}
