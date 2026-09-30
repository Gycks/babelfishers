from collections.abc import Callable, Mapping

from babelfishers.core.parsers.parser import Parser
from babelfishers.core.parsers.registry import parsers_registry
from babelfishers.models.translation_resource import TranslationResourceType


class ParserFactory:
    @staticmethod
    def create(
        parser_type: TranslationResourceType,
        source_locale: str | None = None,
        translated_from: Callable[[str, str], Mapping[str, str]] | None = None,
    ) -> Parser:
        """
        Creates a parser instance for the specified type.

        Args:
            parser_type: The parser to instantiate.
            source_locale: The source locale the configuration declares.
            translated_from: Looks up, by source path and target locale, the hash of the source
                text each unit was last translated from. Formats that keep every locale in the
                source file use it to tell a translation waiting for review from one whose source
                changed. The others ignore it.

        Returns:
            An instance of the Parser associated with that type.
        """

        cls = parsers_registry.get(parser_type)
        if cls is None:
            raise ValueError(f"No class registered for {parser_type}")

        parser = cls(source_locale=source_locale)
        if not isinstance(parser, Parser):
            raise ValueError(f"Invalid translator: {parser_type}")

        if translated_from is not None:
            parser.use_translated_from(translated_from)

        return parser
