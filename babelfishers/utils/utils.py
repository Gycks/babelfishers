import os


def get_env(name: str) -> str:
    if name == "" or name == " " or name is None:
        raise KeyError(f"Environment variable {name} is not set")

    value = os.getenv(name)
    if value is None:
        raise KeyError(f"Environment variable {name} is not set")

    return value
