import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from babelfishers.core.ci_runners.bitbucket import BitbucketRunner
from babelfishers.core.ci_runners.errors import CIError
from babelfishers.core.ci_runners.github import GithubRunner
from babelfishers.core.ci_runners.gitlab import GitlabRunner


@pytest.fixture
def calls():
    return []


def _record(runner, calls, response):
    def fake(method, url, headers, body=None):
        calls.append((method, url, headers, body))
        return response

    runner._request = fake


def _query(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


@pytest.fixture
def github_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("BF_GITHUB_TOKEN", "gh-token")


@pytest.fixture
def gitlab_env(monkeypatch):
    monkeypatch.setenv("CI_API_V4_URL", "https://gitlab.example.com/api/v4")
    monkeypatch.setenv("CI_PROJECT_ID", "42")
    monkeypatch.setenv("CI_SERVER_URL", "https://gitlab.example.com")
    monkeypatch.setenv("CI_PROJECT_PATH", "group/project")
    monkeypatch.setenv("BF_GITLAB_TOKEN", "gl-token")


@pytest.fixture
def bitbucket_env(monkeypatch):
    monkeypatch.setenv("BITBUCKET_WORKSPACE", "acme")
    monkeypatch.setenv("BITBUCKET_REPO_SLUG", "app")
    monkeypatch.setenv("BF_BITBUCKET_TOKEN", "bb-token")


class TestGithubRunner:
    def test_current_branch_is_the_ref_name(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.delenv("GITHUB_REF_TYPE", raising=False)

        assert GithubRunner().current_branch == "main"

    def test_current_branch_is_unknown_for_a_tag(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "v1.0")
        monkeypatch.setenv("GITHUB_REF_TYPE", "tag")

        assert GithubRunner().current_branch is None

    def test_current_branch_ignores_the_pull_request_target(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.setenv("GITHUB_BASE_REF", "develop")
        monkeypatch.delenv("GITHUB_REF_TYPE", raising=False)

        assert GithubRunner().current_branch == "main"

    @pytest.mark.parametrize(
        ("head_repository", "expected"),
        [
            ({"full_name": "octo/repo"}, False),
            ({"full_name": "someone/repo"}, True),
            (None, True),
        ],
        ids=["same repository", "fork", "deleted fork"],
    )
    def test_detects_a_pull_request_from_a_fork(self, monkeypatch, tmp_path, head_repository, expected):
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"head": {"repo": head_repository}}}))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")

        assert GithubRunner().is_fork_pull_request is expected

    def test_is_no_fork_pull_request_on_other_events(self, monkeypatch, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"head": {"repo": {"full_name": "someone/repo"}}}}))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
        monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")

        assert GithubRunner().is_fork_pull_request is False

    def test_is_no_fork_pull_request_when_the_event_file_cannot_be_read(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "missing.json"))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")

        assert GithubRunner().is_fork_pull_request is False

    def test_pull_request_branch_is_the_head_ref_on_pull_request_events_only(self, monkeypatch):
        monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
        assert GithubRunner().pull_request_branch is None

        monkeypatch.setenv("GITHUB_HEAD_REF", "feature")
        assert GithubRunner().pull_request_branch == "feature"

    def test_finds_an_open_pull_request_by_owner_qualified_head(self, github_env, calls):
        runner = GithubRunner()
        _record(runner, calls, [{"html_url": "https://github.com/octo/repo/pull/3"}])

        found = runner.find_pull_request("bot-branch", "main")

        method, url, headers, _ = calls[0]
        assert (found, method) == ("https://github.com/octo/repo/pull/3", "GET")
        assert url.startswith("https://api.github.com/repos/octo/repo/pulls?")
        assert _query(url) == {"state": ["open"], "head": ["octo:bot-branch"], "base": ["main"]}
        assert headers["Authorization"] == "Bearer gh-token"

    def test_finds_nothing_when_no_pull_request_is_open(self, github_env, calls):
        runner = GithubRunner()
        _record(runner, calls, [])

        assert runner.find_pull_request("bot-branch", "main") is None

    def test_creates_a_pull_request(self, github_env, calls):
        runner = GithubRunner()
        _record(runner, calls, {"html_url": "https://github.com/octo/repo/pull/4"})

        created = runner.create_pull_request("bot-branch", "main", "Title", "Body")

        method, url, _, body = calls[0]
        assert (created, method, url) == (
            "https://github.com/octo/repo/pull/4",
            "POST",
            "https://api.github.com/repos/octo/repo/pulls",
        )
        assert body == {"title": "Title", "head": "bot-branch", "base": "main", "body": "Body"}

    def test_pushes_through_a_url_that_carries_the_personal_access_token(self, github_env):
        assert GithubRunner().push_remote() == "https://x-access-token:gh-token@github.com/octo/repo.git"

    def test_asks_for_a_token_when_it_is_missing(self, github_env, monkeypatch, calls):
        monkeypatch.delenv("BF_GITHUB_TOKEN")
        runner = GithubRunner()
        _record(runner, calls, [])

        with pytest.raises(CIError, match="BF_GITHUB_TOKEN"):
            runner.find_pull_request("bot-branch", "main")


class TestGitlabRunner:
    def test_current_branch_is_the_commit_branch(self, monkeypatch):
        monkeypatch.setenv("CI_COMMIT_BRANCH", "main")

        assert GitlabRunner().current_branch == "main"

    def test_current_branch_is_unknown_without_a_commit_branch_and_never_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.delenv("CI_COMMIT_BRANCH", raising=False)
        monkeypatch.setenv("CI_DEFAULT_BRANCH", "main")
        monkeypatch.setenv("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "develop")

        assert GitlabRunner().current_branch is None

    @pytest.mark.parametrize(
        ("source", "target", "expected"),
        [("group/project", "group/project", False), ("me/project", "group/project", True), (None, None, False)],
        ids=["same project", "fork", "not a merge request"],
    )
    def test_detects_a_merge_request_from_a_fork(self, monkeypatch, source, target, expected):
        for variable, value in (
            ("CI_MERGE_REQUEST_SOURCE_PROJECT_PATH", source),
            ("CI_MERGE_REQUEST_PROJECT_PATH", target),
        ):
            if value is None:
                monkeypatch.delenv(variable, raising=False)
            else:
                monkeypatch.setenv(variable, value)

        assert GitlabRunner().is_fork_pull_request is expected

    def test_pull_request_branch_is_the_merge_request_source_branch_in_merge_request_pipelines_only(self, monkeypatch):
        monkeypatch.delenv("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", raising=False)
        assert GitlabRunner().pull_request_branch is None

        monkeypatch.setenv("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "feature")
        assert GitlabRunner().pull_request_branch == "feature"

    def test_pushes_through_an_authenticated_url(self, gitlab_env):
        assert GitlabRunner().push_remote() == "https://oauth2:gl-token@gitlab.example.com/group/project.git"

    def test_refuses_to_push_without_a_token(self, gitlab_env, monkeypatch):
        monkeypatch.delenv("BF_GITLAB_TOKEN")

        with pytest.raises(CIError, match="BF_GITLAB_TOKEN"):
            GitlabRunner().push_remote()

    def test_finds_an_open_merge_request(self, gitlab_env, calls):
        runner = GitlabRunner()
        _record(runner, calls, [{"web_url": "https://gitlab.example.com/group/project/-/merge_requests/5"}])

        found = runner.find_pull_request("bot-branch", "main")

        method, url, headers, _ = calls[0]
        assert (found, method) == ("https://gitlab.example.com/group/project/-/merge_requests/5", "GET")
        assert url.startswith("https://gitlab.example.com/api/v4/projects/42/merge_requests?")
        assert _query(url) == {"state": ["opened"], "source_branch": ["bot-branch"], "target_branch": ["main"]}
        assert headers == {"PRIVATE-TOKEN": "gl-token"}

    def test_creates_a_merge_request(self, gitlab_env, calls):
        runner = GitlabRunner()
        _record(runner, calls, {"web_url": "https://gitlab.example.com/group/project/-/merge_requests/6"})

        created = runner.create_pull_request("bot-branch", "main", "Title", "Body")

        method, url, _, body = calls[0]
        assert (created, method) == ("https://gitlab.example.com/group/project/-/merge_requests/6", "POST")
        assert url == "https://gitlab.example.com/api/v4/projects/42/merge_requests"
        assert body == {
            "source_branch": "bot-branch",
            "target_branch": "main",
            "title": "Title",
            "description": "Body",
            "remove_source_branch": True,
        }


class TestBitbucketRunner:
    def test_current_branch_is_the_pipeline_branch_and_unknown_without_one(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_BRANCH", "main")
        monkeypatch.setenv("BITBUCKET_PR_DESTINATION_BRANCH", "develop")
        assert BitbucketRunner().current_branch == "main"

        monkeypatch.delenv("BITBUCKET_BRANCH")
        assert BitbucketRunner().current_branch is None

    def test_cannot_tell_a_fork_pull_request(self):
        assert BitbucketRunner().is_fork_pull_request is False

    def test_pull_request_branch_is_the_branch_only_when_the_pipeline_is_for_a_pull_request(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_BRANCH", "feature")
        monkeypatch.delenv("BITBUCKET_PR_ID", raising=False)
        assert BitbucketRunner().pull_request_branch is None

        monkeypatch.setenv("BITBUCKET_PR_ID", "12")
        assert BitbucketRunner().pull_request_branch == "feature"

    def test_finds_an_open_pull_request(self, bitbucket_env, calls):
        runner = BitbucketRunner()
        page = {"values": [{"links": {"html": {"href": "https://bitbucket.org/acme/app/pull-requests/8"}}}]}
        _record(runner, calls, page)

        found = runner.find_pull_request("bot-branch", "main")

        method, url, headers, _ = calls[0]
        assert (found, method) == ("https://bitbucket.org/acme/app/pull-requests/8", "GET")
        assert url.startswith("https://api.bitbucket.org/2.0/repositories/acme/app/pullrequests?")
        assert _query(url) == {
            "state": ["OPEN"],
            "q": ['source.branch.name="bot-branch" AND destination.branch.name="main"'],
        }
        assert headers == {"Authorization": "Bearer bb-token"}

    def test_pushes_through_a_url_that_carries_the_repository_access_token(self, bitbucket_env):
        assert BitbucketRunner().push_remote() == "https://x-token-auth:bb-token@bitbucket.org/acme/app.git"

    def test_finds_nothing_when_the_page_is_empty(self, bitbucket_env, calls):
        runner = BitbucketRunner()
        _record(runner, calls, {"values": []})

        assert runner.find_pull_request("bot-branch", "main") is None

    def test_creates_a_pull_request(self, bitbucket_env, calls):
        runner = BitbucketRunner()
        _record(runner, calls, {"links": {"html": {"href": "https://bitbucket.org/acme/app/pull-requests/9"}}})

        created = runner.create_pull_request("bot-branch", "main", "Title", "Body")

        method, url, _, body = calls[0]
        assert (created, method) == ("https://bitbucket.org/acme/app/pull-requests/9", "POST")
        assert url == "https://api.bitbucket.org/2.0/repositories/acme/app/pullrequests"
        assert body == {
            "title": "Title",
            "description": "Body",
            "source": {"branch": {"name": "bot-branch"}},
            "destination": {"branch": {"name": "main"}},
            "close_source_branch": True,
        }


class _Handler(BaseHTTPRequestHandler):
    seen: list[tuple[str, str, str | None, bytes]] = []

    def _respond(self):
        length = int(self.headers.get("Content-Length") or 0)
        _Handler.seen.append((self.command, self.path, self.headers.get("X-Test"), self.rfile.read(length)))
        status = 404 if self.path == "/missing" else 200
        payload = json.dumps({"error": "nope"} if status == 404 else {"ok": True}).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = _respond  # noqa: N815

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Handler.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


class TestRequest:
    def test_sends_the_headers_and_the_json_body_and_parses_the_json_answer(self, server):
        answer = GithubRunner()._request("POST", f"{server}/pulls", {"X-Test": "1"}, {"title": "Hi"})

        assert answer == {"ok": True}
        assert _Handler.seen == [("POST", "/pulls", "1", b'{"title": "Hi"}')]

    def test_reports_an_http_error_with_its_status(self, server):
        with pytest.raises(CIError, match="HTTP 404"):
            GithubRunner()._request("GET", f"{server}/missing", {})

    def test_reports_an_unreachable_server(self):
        with pytest.raises(CIError, match="failed"):
            GithubRunner()._request("GET", "http://127.0.0.1:1/", {})
