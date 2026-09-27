from collections.abc import Callable

from babelfishers.models.extract import ExtractType


code_scanners_registry: dict[ExtractType, type] = {}


def register(extract_type: ExtractType) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        code_scanners_registry[extract_type] = cls
        return cls

    return decorator
