import logging
from pathlib import Path

from babelfishers.core.guards.cldr import required_plural_categories
from babelfishers.core.guards.glossary_guard import GlossaryGuard
from babelfishers.core.guards.placeholder_guard import PlaceholderGuard
from babelfishers.core.guards.toolkit import find_placeholders
from babelfishers.core.tm_store import TMStore
from babelfishers.core.translators.translator_factory import TranslatorFactory
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary
from babelfishers.models.plan import VolumeEstimate
from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import ParseResult, TranslationUnit
from babelfishers.utils.console_formater import ConsoleFormatter


_PLURAL_GROUPED_RESOURCE_TYPES = (TranslationResourceType.ANDROID_STRINGS, TranslationResourceType.FLUTTER_ARB)
_CLDR_CATEGORY_NAMES = {"zero", "one", "two", "few", "many", "other"}


class TranslationPipeline:
    def __init__(
        self,
        translation_engines: list[Engine],
        glossary: Glossary | None,
        translation_store: TMStore | None,
    ) -> None:

        self._logger: logging.Logger = logging.getLogger(__name__)
        self._translation_engines: list[Engine] = translation_engines
        self._glossary: Glossary | None = glossary
        self._translation_store: TMStore | None = translation_store

    def _lookup_cache(
        self, units: list[TranslationUnit], source: str, target: str
    ) -> list[tuple[TranslationUnit, str | None]]:
        store = self._translation_store
        if store is None:
            return [(unit, None) for unit in units]

        return [(unit, store.lookup(unit.source_text, source, target)) for unit in units]

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

        for unit, cached in self._lookup_cache(units, source, target):
            if cached is not None:
                unit.translated_text = cached
                hits.append(unit)
                hit_keys.append(TMStore.make_key(unit.source_text, source, target))
            else:
                misses.append(unit)

        if self._translation_store is not None:
            self._translation_store.bump_last_used_for_keys(hit_keys)

        return hits, misses

    def _units_sent_to_provider(self, units: list[TranslationUnit], target_locale: str) -> list[TranslationUnit]:
        """
        Apply the same protection guards as a real run, using the engine that would be
        tried first, and return the units that would actually reach the provider.
        """
        if not units:
            return []

        engine = self._translation_engines[0]
        protected = PlaceholderGuard(engine).protect(units)
        if self._glossary:
            protected = GlossaryGuard(self._glossary, target_locale, engine).protect(protected)

        return [unit for unit in protected if not unit.skip_translation]

    def plan(self, parse_result: ParseResult, source_locale: str, target_locale: str) -> VolumeEstimate:
        """
        Estimate what `run` would send to the provider, without translating, writing
        or touching the translation memory.

        The cached/uncached split is exact. The character count is an estimate: it
        assumes no retry or fallback engine is needed.

        Args:
            parse_result: The parsed source document.
            source_locale: Source language code.
            target_locale: Target language code.

        Returns:
            The unit counts and the number of characters that would be sent.
        """
        self._warn_on_missing_plural_categories(parse_result.units, target_locale)

        lookups = self._lookup_cache(parse_result.units, source_locale, target_locale)
        misses = [unit for unit, cached in lookups if cached is None]
        outgoing = self._units_sent_to_provider(misses, target_locale)

        return VolumeEstimate(
            units_total=len(parse_result.units),
            cached_units=len(parse_result.units) - len(misses),
            units_to_translate=len(outgoing),
            characters=sum(len(unit.source_text) for unit in outgoing),
        )

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

            retries = 2
            retries_counter = 0
            for _ in range(retries):
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
                    if retries_counter < retries - 1:
                        self._logger.warning(
                            ConsoleFormatter.error("An error occurred during translation. Retrying..."), exc_info=exe
                        )

                finally:
                    retries_counter += 1

            self._logger.warning(
                ConsoleFormatter.warning("An error occurred during translation. Switching engine (if any)")
            )

        raise ValueError("The translation pipeline failed.")

    def _warn_on_placeholder_mismatch(self, units: list[TranslationUnit]) -> None:
        for unit in units:
            if unit.skip_translation:
                continue

            source_tokens = {p.matched_text for p in find_placeholders(unit.source_text, unit.unit_type)}
            translated_tokens = {p.matched_text for p in find_placeholders(unit.translated_text, unit.unit_type)}

            if source_tokens != translated_tokens:
                self._logger.warning(
                    ConsoleFormatter.warning(
                        f"Placeholder mismatch for unit '{unit.key}': "
                        f"expected {sorted(source_tokens)}, got {sorted(translated_tokens)}"
                    )
                )

    @staticmethod
    def _group_plural_units(
        units: list[TranslationUnit],
    ) -> dict[tuple[TranslationResourceType, str], dict[str, TranslationUnit]]:
        groups: dict[tuple[TranslationResourceType, str], dict[str, TranslationUnit]] = {}

        for unit in units:
            if unit.unit_type not in _PLURAL_GROUPED_RESOURCE_TYPES:
                continue

            base_key, separator, category = unit.key.rpartition(".")
            if not separator or category not in _CLDR_CATEGORY_NAMES:
                continue

            groups.setdefault((unit.unit_type, base_key), {})[category] = unit

        return groups

    def _warn_on_missing_plural_categories(self, units: list[TranslationUnit], target_locale: str) -> None:
        required = required_plural_categories(target_locale)

        for (unit_type, base_key), members in self._group_plural_units(units).items():
            missing = required - members.keys()
            if missing:
                self._logger.warning(
                    ConsoleFormatter.warning(
                        f"[{target_locale}] Plural group '{base_key}' ({unit_type}) is missing required "
                        f"CLDR categories: {sorted(missing)}"
                    )
                )

    def run(self, parse_result: ParseResult, source_locale: str, target_locale: str, destination_path: Path) -> None:
        self._warn_on_missing_plural_categories(parse_result.units, target_locale)
        cache_hits, cache_misses = self._cache_split_translation_units(parse_result.units, source_locale, target_locale)
        engine_used, translated_copies = self._run_translate(cache_misses, source_locale, target_locale)

        for original_unit, translated_copy in zip(cache_misses, translated_copies, strict=True):
            original_unit.translated_text = translated_copy.translated_text

        all_original_units = cache_hits + cache_misses
        self._warn_on_placeholder_mismatch(all_original_units)

        for unit in all_original_units:
            unit.write_back(unit.translated_text)

        parse_result.save(destination_path)

        if self._translation_store is not None:
            query_data = [
                (unit.source_text, source_locale, target_locale, unit.translated_text) for unit in cache_misses
            ]
            self._translation_store.store_batch(query_data, engine_used)
