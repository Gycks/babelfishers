import logging
from pathlib import Path

from babelfishers.core.guards.glossary_guard import GlossaryGuard
from babelfishers.core.guards.placeholder_guard import PlaceholderGuard
from babelfishers.core.tm_store import TMStore
from babelfishers.core.translators.translator_factory import TranslatorFactory
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


class TranslationPipeline:
    def __init__(
        self,
        translation_engines: list[Engine],
        glossary: Glossary | None,
        translation_store: TMStore,
        dry_run: bool = False,
    ) -> None:

        self._logger: logging.Logger = logging.getLogger(__file__)
        self._translation_engines: list[Engine] = translation_engines
        self._glossary: Glossary | None = glossary
        self._translation_store: TMStore = translation_store
        self._dry_run: bool = dry_run

    def _cache_split_translation_units(
        self, units: list[TranslationUnit], source: str, target: str
    ) -> tuple[list[TranslationUnit], list[TranslationUnit]]:
        """
        Split translation units into cache hits and cache misses.

        Looks up each translation unit in the translation cache using its source
        text and the specified language pair. For cache hits, the cached
        translation is assigned to `unit.translated_text`. Translation units
        that are not found in the cache are returned as cache misses.

        Args:
            units: Translation units to look up in the cache.
            source: Source language code.
            target: Target language code.

        Returns:
            A tuple containing:
                - A list of translation units found in the cache.
                - A list of translation units not found in the cache.
        """
        hits = []
        hit_keys = []
        misses = []

        for unit in units:
            cache = self._translation_store.lookup(unit.source_text, source, target)
            if cache is not None:
                unit.translated_text = cache
                hits.append(unit)
                hit_keys.append(TMStore.make_key(unit.source_text, source, target))
            else:
                misses.append(unit)

        self._translation_store.bump_last_used_for_keys(hit_keys)

        return hits, misses

    def _run_translate(
        self,
        units: list[TranslationUnit],
        source_locale: str,
        target_locale: str,
    ) -> tuple[Engine, list[TranslationUnit]]:

        for engine in self._translation_engines:
            translator = TranslatorFactory.create(engine)

            self._logger.info(ConsoleFormatter.info(f"Using translation engine: {translator.engine}"))

            placeholder_guard = PlaceholderGuard(engine)
            protected_units = placeholder_guard.protect(units)

            for _ in range(2):
                try:
                    dataset = protected_units
                    glossary_guard: GlossaryGuard | None = None
                    if self._glossary:
                        glossary_guard = GlossaryGuard(
                            self._glossary,
                            target_locale,
                            translator.engine,
                        )
                        dataset = glossary_guard.protect(protected_units)

                    translations = translator.translate(
                        dataset,
                        source_locale,
                        target_locale,
                    )

                    if glossary_guard:
                        if not glossary_guard.restore(translations):
                            raise ValueError("Unable to restore translation units.")

                    if not placeholder_guard.restore(translations):
                        raise ValueError("Unable to restore translation units.")

                    return translator.engine, translations

                except Exception as exe:
                    self._logger.warning(
                        ConsoleFormatter.error("An error occurred during translation. Retrying..."), exc_info=exe
                    )

            self._logger.warning(
                ConsoleFormatter.warning("An error occurred during translation. Switching engine (if any)")
            )

        raise ValueError("The translation pipeline failed.")

    def run(self, parse_result: ParseResult, source_locale: str, target_locale: str, destination_path: Path) -> None:
        cache_hits, cache_misses = self._cache_split_translation_units(parse_result.units, source_locale, target_locale)
        engine_used, translated_copies = self._run_translate(cache_misses, source_locale, target_locale)

        for original_unit, translated_copy in zip(cache_misses, translated_copies, strict=True):
            original_unit.translated_text = translated_copy.translated_text

        all_original_units = cache_hits + cache_misses

        for unit in all_original_units:
            unit.write_back(unit.translated_text)

        parse_result.save(destination_path)

        query_data = [(unit.source_text, source_locale, target_locale, unit.translated_text) for unit in cache_misses]
        self._translation_store.store_batch(query_data, engine_used)
