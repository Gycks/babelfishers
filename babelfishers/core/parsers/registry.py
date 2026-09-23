from collections.abc import Callable

from babelfishers.models.translation_resource import TranslationResourceType


parsers_registry: dict[TranslationResourceType, type] = {}


def register(parser_type: TranslationResourceType) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        parsers_registry[parser_type] = cls
        return cls

    return decorator
