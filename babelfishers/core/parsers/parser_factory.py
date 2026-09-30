from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import parsers_registry
from babelfishers.models.translation_resource import TranslationResourceType


class ParserFactory:
    @staticmethod
    def create(parser_type: TranslationResourceType, source_locale: str | None = None) -> Parser:
        """
        Creates a parser instance for the specified type.

        Args:
            parser_type: The parser to instantiate.
            source_locale: The source locale the configuration declares.

        Returns:
            An instance of the Parser associated with that type.
        """

        cls = parsers_registry.get(parser_type)
        if cls is None:
            raise ValueError(f"No class registered for {parser_type}")

        parser = cls(source_locale=source_locale)
        if not isinstance(parser, Parser):
            raise ValueError(f"Invalid translator: {parser_type}")

        return parser
