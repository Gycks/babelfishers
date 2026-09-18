import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from babelfishers import APPLICATION_NAME


def get_env(name: str) -> str:
    if name == "" or name == " " or name is None:
        raise KeyError(f"Environment variable {name} is not set")

    value = os.getenv(name)
    if value is None:
        raise KeyError(f"Environment variable {name} is not set")

    return value


def get_working_space() -> Path:
    path = Path.cwd().resolve()
    path = path.joinpath(f".{APPLICATION_NAME}")
    path.mkdir(exist_ok=True)
    return path


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
    fd, tmp_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)

    try:
        writer(tmp_path)
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"
