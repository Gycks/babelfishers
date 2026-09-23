from enum import StrEnum


class CIRunnerType(StrEnum):
    GITLAB = "gitlab"
    GITHUB = "github"
    # BITBUCKET = "bitbucket"


# from .bitbucket import BitbucketRunner  # noqa: E402, F401
from .github import GithubRunner  # noqa: E402, F401
from .gitlab import GitlabRunner  # noqa: E402, F401
