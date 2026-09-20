import urllib.parse

from babelfishers.core.ci_runners import CIRunnerType
from babelfishers.core.ci_runners.runner import BaseRunner, register
from babelfishers.utils.utils import get_env


_API_URL = "https://api.bitbucket.org/2.0"


@register(CIRunnerType.BITBUCKET)
class BitbucketRunner(BaseRunner):
    @property
    def name(self) -> str:
        return "Bitbucket Pipelines"

    @property
    def required_env(self) -> tuple[str, ...]:
        return "CI", "BITBUCKET_BUILD_NUMBER", "BITBUCKET_WORKSPACE", "BITBUCKET_REPO_SLUG", "BITBUCKET_COMMIT"

    @property
    def token_env(self) -> str:
        return "BF_BITBUCKET_TOKEN"

    @property
    def token_hint(self) -> str:
        return (
            "Bitbucket Pipelines gives a job no token for its API. Pass a repository access token with "
            "repository write and pull request write access."
        )

    @property
    def current_branch(self) -> str | None:
        return get_env("BITBUCKET_BRANCH", raise_on_error=False) or None

    @property
    def pull_request_branch(self) -> str | None:
        if not get_env("BITBUCKET_PR_ID", raise_on_error=False):
            return None

        return get_env("BITBUCKET_BRANCH", raise_on_error=False) or None

    def push_remote(self) -> str:
        workspace, slug = get_env("BITBUCKET_WORKSPACE"), get_env("BITBUCKET_REPO_SLUG")
        return f"https://x-token-auth:{self._token()}@bitbucket.org/{workspace}/{slug}.git"

    def find_pull_request(self, branch: str, base: str) -> str | None:
        query = urllib.parse.urlencode(
            {"state": "OPEN", "q": f'source.branch.name="{branch}" AND destination.branch.name="{base}"'}
        )

        page = self._request("GET", f"{self._pull_requests_url()}?{query}", self._headers())

        return page["values"][0]["links"]["html"]["href"] if page["values"] else None

    def create_pull_request(self, branch: str, base: str, title: str, body: str) -> str:
        created = self._request(
            "POST",
            self._pull_requests_url(),
            self._headers(),
            {
                "title": title,
                "description": body,
                "source": {"branch": {"name": branch}},
                "destination": {"branch": {"name": base}},
                "close_source_branch": True,
            },
        )
        return str(created["links"]["html"]["href"])

    @staticmethod
    def _pull_requests_url() -> str:
        workspace, slug = get_env("BITBUCKET_WORKSPACE"), get_env("BITBUCKET_REPO_SLUG")
        return f"{_API_URL}/repositories/{workspace}/{slug}/pullrequests"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}
