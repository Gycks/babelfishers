import json
import urllib.parse
from pathlib import Path

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.runner import BaseRunner, register
from babelfishers.utils.utils import get_env


@register(CIRunnerType.GITHUB)
class GithubRunner(BaseRunner):
    @property
    def name(self) -> str:
        return "GitHub Actions"

    @property
    def required_env(self) -> tuple[str, ...]:
        return "GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_REF_NAME", "GITHUB_SERVER_URL", "GITHUB_API_URL"

    @property
    def token_env(self) -> str:
        return "BF_GITHUB_TOKEN"

    @property
    def token_hint(self) -> str:
        return (
            "The GITHUB_TOKEN of GitHub Actions is not used: commits pushed with it do not start other workflows, "
            "so the pull request's own checks would never run. Pass a personal access token with write access "
            "to the repository's contents and pull requests."
        )

    @property
    def current_branch(self) -> str | None:
        if get_env("GITHUB_REF_TYPE", raise_on_error=False) == "tag":
            return None

        return get_env("GITHUB_REF_NAME", raise_on_error=False) or None

    @property
    def pull_request_branch(self) -> str | None:
        return get_env("GITHUB_HEAD_REF", raise_on_error=False) or None

    @property
    def is_fork_pull_request(self) -> bool:
        event_path = get_env("GITHUB_EVENT_PATH", raise_on_error=False)
        if not event_path or get_env("GITHUB_EVENT_NAME", raise_on_error=False) not in (
            "pull_request",
            "pull_request_target",
        ):
            return False

        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False

        head_repository = ((event.get("pull_request") or {}).get("head") or {}).get("repo")
        return head_repository is None or head_repository.get("full_name") != get_env("GITHUB_REPOSITORY")

    def push_remote(self) -> str:
        server = urllib.parse.urlparse(get_env("GITHUB_SERVER_URL"))
        return f"{server.scheme}://x-access-token:{self._token()}@{server.netloc}/{get_env('GITHUB_REPOSITORY')}.git"

    def find_pull_request(self, branch: str, base: str) -> str | None:
        owner = get_env("GITHUB_REPOSITORY").split("/")[0]
        query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{branch}", "base": base})

        pull_requests = self._request("GET", f"{self._pulls_url()}?{query}", self._headers())

        return pull_requests[0]["html_url"] if pull_requests else None

    def create_pull_request(self, branch: str, base: str, title: str, body: str) -> str:
        created = self._request(
            "POST", self._pulls_url(), self._headers(), {"title": title, "head": branch, "base": base, "body": body}
        )
        return str(created["html_url"])

    @staticmethod
    def _pulls_url() -> str:
        return f"{get_env('GITHUB_API_URL')}/repos/{get_env('GITHUB_REPOSITORY')}/pulls"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "X-GitHub-Api-Version": "2022-11-28"}
