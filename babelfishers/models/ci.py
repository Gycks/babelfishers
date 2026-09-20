from pydantic import BaseModel, ConfigDict

from babelfishers import APPLICATION_NAME
from babelfishers.core.ci_runners import CIRunnerType


BOT_BRANCH_PREFIX = f"{APPLICATION_NAME}/translations/"
_SAFE_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-")


def _encode_branch_component(name: str) -> str:
    return "".join(chr(byte) if chr(byte) in _SAFE_CHARACTERS else f"_{byte:02X}" for byte in name.encode("utf-8"))


def _shorten(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def bot_branch_name(base_branch: str) -> str:
    """
    The branch the bot keeps its translation changes on for `base_branch`.

    Each base branch gets exactly one bot branch, so runs on the same base reuse it, and no two base branches
    share one. Example: "main" gives "babelfishers/translations/main", "release/1.0"
    gives "babelfishers/translations/release_2F1.0".
    """
    if not base_branch:
        raise ValueError("The base branch must be known before the bot branch name can be derived.")

    return f"{BOT_BRANCH_PREFIX}{_encode_branch_component(base_branch)}"


def is_bot_branch(branch: str) -> bool:
    return branch.startswith(BOT_BRANCH_PREFIX)


class CIRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: CIRunnerType
    pull_request: bool  # True opens a new pull request, False updates the current one
    pull_request_title: str = ""
    pull_request_body: str = "Babel Fishers bot: Localization workflow completed successfully."
    commit_message: str = "chore: update translations"

    def __repr__(self) -> str:
        fields: dict[str, object] = {"platform": self.platform.value, "pull_request": self.pull_request}
        for name in ("pull_request_title", "pull_request_body", "commit_message"):
            value: str = getattr(self, name)
            if value:
                fields[name] = _shorten(value)

        return f"{type(self).__name__}({', '.join(f'{name}={value!r}' for name, value in fields.items())})"

    __str__ = __repr__
