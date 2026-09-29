import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path
from secrets import token_hex

from babelfishers import APPLICATION_NAME


def get_env(name: str, raise_on_error: bool = True) -> str:
    if name == "" or name == " " or name is None:
        raise KeyError(f"Environment variable {name} is not set")

    value = os.getenv(name)
    if value is None:
        if not raise_on_error:
            return ""
        raise KeyError(f"Environment variable {name} is not set")

    return value


def get_working_space() -> Path:
    return Path.cwd().resolve().joinpath(f".{APPLICATION_NAME}")


def get_translation_store_storage_path() -> Path:
    path = get_working_space()
    return path.joinpath("store.sqlite")


def get_run_lock_storage_path() -> Path:
    path = get_working_space()
    return path.joinpath("run.lock")


def hash_file_contents(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_app_config_storage_path() -> Path:
    path = Path.cwd().resolve()
    return path.joinpath(f"{APPLICATION_NAME}.toml")


def atomic_write(destination: Path, writer: Callable[[Path], object]) -> None:
    """
    Writes to a temp file in the destination's own directory, then atomically
    renames it into place, so a crash mid-write can never leave a corrupted
    or half-written file at `destination`.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(f".{destination.name}.{token_hex(8)}.tmp")
    os.close(os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666))

    try:
        writer(tmp_path)
        if destination.exists():
            tmp_path.chmod(stat.S_IMODE(destination.stat().st_mode))
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"
