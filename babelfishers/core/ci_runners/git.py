import subprocess
from collections.abc import Sequence
from pathlib import Path

from babelfishers.core.ci_runners.errors import CIError


class Git:
    """Thin wrapper over the git command line."""

    def __init__(self, cwd: Path | None = None, secrets: Sequence[str] = ()) -> None:
        self._cwd = cwd
        self._secrets = tuple(secret for secret in secrets if secret)

    def _run(self, *args: str, check: bool = True, network: bool = False) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(  # noqa: S603
            ["git", *(self._without_saved_authorization() if network else []), *args],  # noqa: S607
            cwd=self._cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise CIError(f"git {args[0]} failed: {self._redact(result.stderr.strip() or result.stdout.strip())}")

        return result

    def _without_saved_authorization(self) -> list[str]:
        # A checkout can save the platform's own token as an Authorization header in the git config. Git sends that
        # header with every request and it wins over the credentials in the remote URL, so a push would go out
        # under the wrong token. Clearing each such key for the command lets the URL's credentials be used.
        result = self._run("config", "--get-regexp", r"^http\..*extraheader$", check=False)
        keys = dict.fromkeys(
            key
            for key, _, value in (line.partition(" ") for line in result.stdout.splitlines())
            if value.strip().lower().startswith("authorization:")
        )
        return [argument for key in keys for argument in ("-c", f"{key}=")]

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def head_author(self) -> tuple[str, str]:
        """The name and email of the author of the current commit."""
        name, email = self._run("log", "-1", "--format=%an%n%ae").stdout.strip().split("\n")
        return name, email

    def head_commit(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()

    def remote_tip(self, remote: str, branch: str) -> str | None:
        """The commit `branch` points to on `remote`, or None when the branch does not exist there."""
        output = self._run("ls-remote", "--heads", remote, f"refs/heads/{branch}", network=True).stdout.strip()
        return output.split()[0] if output else None

    def stage(self, paths: Sequence[Path]) -> None:
        self._run("add", "--force", "--", *(str(path) for path in paths))

    def has_staged_changes(self) -> bool:
        return self._run("diff", "--cached", "--quiet", check=False).returncode == 1

    def checkout_branch(self, branch: str) -> None:
        self._run("checkout", "-B", branch)

    def commit(self, message: str, author_name: str, author_email: str) -> None:
        self._run(
            "-c", f"user.name={author_name}", "-c", f"user.email={author_email}", "commit", "--no-verify", "-m", message
        )

    def push(self, remote: str, refspec: str, force: bool = False) -> None:
        self._run("push", *(["--force"] if force else []), remote, refspec, network=True)
