import os
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
    path.joinpath(APPLICATION_NAME)
    path.mkdir(exist_ok=True)
    return path


def get_translation_store_storage_path() -> Path:
    path = get_working_space()
    return path.joinpath("store.sqlite")
