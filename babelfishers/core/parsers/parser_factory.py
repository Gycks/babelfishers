from collections.abc import Callable

from babelfishers.core.parsers.parser import Parser
from babelfishers.models.translation_resource import TranslationResourceType


_registry: dict[TranslationResourceType, type] = {}


def register(parser_type: TranslationResourceType) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _registry[parser_type] = cls
        return cls

    return decorator


class ParserFactory:
    @staticmethod
    def create(parser_type: TranslationResourceType) -> Parser:
        """
        Creates a parser instance for the specified type.

        Args:
            parser_type: The parser to instantiate.

        Returns:
            An instance of the Parser associated with that type.
        """

        cls = _registry.get(parser_type)
        if cls is None:
            raise ValueError(f"No class registered for {parser_type}")

        parser = cls()
        if not isinstance(parser, Parser):
            raise ValueError(f"Invalid translator: {parser_type}")

        return parser
