import urllib.parse

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.runner import BaseRunner, register
from babelfishers.utils.utils import get_env


@register(CIRunnerType.GITLAB)
class GitlabRunner(BaseRunner):
    @property
    def name(self) -> str:
        return "GitLab CI/CD"

    @property
    def required_env(self) -> tuple[str, ...]:
        return "GITLAB_CI", "CI_PROJECT_ID", "CI_SERVER_URL", "CI_API_V4_URL", "CI_COMMIT_REF_NAME", "CI_DEFAULT_BRANCH"

    @property
    def token_env(self) -> str:
        return "BF_GITLAB_TOKEN"

    @property
    def token_hint(self) -> str:
        return (
            "The job token GitLab provides cannot open merge requests. Pass a project access token with the "
            "api and write_repository scopes."
        )

    @property
    def current_branch(self) -> str | None:
        return get_env("CI_COMMIT_BRANCH", raise_on_error=False) or None

    @property
    def pull_request_branch(self) -> str | None:
        return get_env("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", raise_on_error=False) or None

    @property
    def is_fork_pull_request(self) -> bool:
        source = get_env("CI_MERGE_REQUEST_SOURCE_PROJECT_PATH", raise_on_error=False)
        target = get_env("CI_MERGE_REQUEST_PROJECT_PATH", raise_on_error=False)
        return bool(source and target and source != target)

    def push_remote(self) -> str:
        server = urllib.parse.urlparse(get_env("CI_SERVER_URL"))
        return f"{server.scheme}://oauth2:{self._token()}@{server.netloc}/{get_env('CI_PROJECT_PATH')}.git"

    def find_pull_request(self, branch: str, base: str) -> str | None:
        query = urllib.parse.urlencode({"state": "opened", "source_branch": branch, "target_branch": base})

        merge_requests = self._request("GET", f"{self._merge_requests_url()}?{query}", self._headers())

        return merge_requests[0]["web_url"] if merge_requests else None

    def create_pull_request(self, branch: str, base: str, title: str, body: str) -> str:
        created = self._request(
            "POST",
            self._merge_requests_url(),
            self._headers(),
            {
                "source_branch": branch,
                "target_branch": base,
                "title": title,
                "description": body,
                "remove_source_branch": True,
            },
        )
        return str(created["web_url"])

    @staticmethod
    def _merge_requests_url() -> str:
        return f"{get_env('CI_API_V4_URL')}/projects/{get_env('CI_PROJECT_ID')}/merge_requests"

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._token()}
