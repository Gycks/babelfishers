from collections.abc import Callable

from babelfishers.models.engine import Engine


translators_registry: dict[Engine, type] = {}


def register(engine_type: Engine) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        translators_registry[engine_type] = cls
        return cls

    return decorator
