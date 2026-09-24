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

        lookups = []
        for unit in units:
            cached = store.lookup(unit.source_text, source, target)
            # An entry with broken placeholders (stored by an older version) is translated again.
            if cached is not None and not self._placeholders_match(unit.source_text, cached, unit.unit_type):
                cached = None
            lookups.append((unit, cached))

        return lookups

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
    ) -> dict[int, tuple[Engine, TranslationUnit]]:
        """
        Translate the units, retrying and switching engine on errors and on units whose
        placeholders did not come back intact.

        Returns:
            The translated copies with the engine that produced them, keyed by their position
            in `units`. Units whose placeholders never came back intact, or that the last engine
            failed on after others were translated, are left out.

        Raises:
            ValueError: When the last engine failed and no unit was translated.
        """
        results: dict[int, tuple[Engine, TranslationUnit]] = {}
        rejected: dict[int, str] = {}
        pending = list(range(len(units)))
        last_attempt_failed = False

        for engine in self._translation_engines:
            translator = TranslatorFactory.create(engine)

            self._logger.info(ConsoleFormatter.info(f"Using translation engine: {translator.engine}"))

            retries = 2
            retries_counter = 0
            for _ in range(retries):
                placeholder_guard = PlaceholderGuard(engine)
                protected_units = placeholder_guard.protect([units[i] for i in pending])

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

                    last_attempt_failed = False
                    mismatched = []
                    for i, translation in zip(pending, translations, strict=True):
                        if translation.skip_translation or self._placeholders_match(
                            units[i].source_text, translation.translated_text, units[i].unit_type
                        ):
                            results[i] = (translator.engine, translation)
                        else:
                            mismatched.append(i)
                            rejected[i] = translation.translated_text

                    pending = mismatched
                    if not pending:
                        return results

                    if retries_counter < retries - 1:
                        self._logger.warning(
                            ConsoleFormatter.warning(
                                f"{len(pending)} unit(s) came back with changed placeholders. Retrying..."
                            )
                        )

                except Exception as exe:
                    last_attempt_failed = True
                    if retries_counter < retries - 1:
                        self._logger.warning(
                            ConsoleFormatter.error("An error occurred during translation. Retrying..."), exc_info=exe
                        )

                finally:
                    retries_counter += 1

            reason = (
                "An error occurred during translation"
                if last_attempt_failed
                else f"{len(pending)} unit(s) still came back with changed placeholders"
            )
            self._logger.warning(ConsoleFormatter.warning(f"{reason}. Switching engine (if any)"))

        # Nothing to keep: the provider itself is failing (wrong key, quota, network).
        if last_attempt_failed and not results:
            raise ValueError("The translation pipeline failed.")

        for i in pending:
            if last_attempt_failed:
                self._logger.warning(
                    ConsoleFormatter.warning(
                        f"Translation failed for unit '{units[i].key}' on every engine. Left untranslated."
                    )
                )
            else:
                self._warn_left_untranslated(units[i], rejected[i])

        return results

    @staticmethod
    def _placeholders(text: str, unit_type: TranslationResourceType) -> list[str]:
        return sorted(p.matched_text for p in find_placeholders(text, unit_type))

    @classmethod
    def _placeholders_match(cls, source_text: str, translated_text: str, unit_type: TranslationResourceType) -> bool:
        return cls._placeholders(source_text, unit_type) == cls._placeholders(translated_text, unit_type)

    def _warn_left_untranslated(self, unit: TranslationUnit, translated_text: str) -> None:
        self._logger.warning(
            ConsoleFormatter.warning(
                f"Placeholder mismatch for unit '{unit.key}': "
                f"expected {self._placeholders(unit.source_text, unit.unit_type)}, "
                f"got {self._placeholders(translated_text, unit.unit_type)}. Left untranslated."
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

    def run(self, parse_result: ParseResult, source_locale: str, target_locale: str, destination_path: Path) -> int:
        """
        Translate, write the target file and save the new translations in the memory.

        Returns:
            How many units were left untranslated. They keep the source file's value.
        """
        self._warn_on_missing_plural_categories(parse_result.units, target_locale)
        cache_hits, cache_misses = self._cache_split_translation_units(parse_result.units, source_locale, target_locale)
        translated_copies = self._run_translate(cache_misses, source_locale, target_locale)

        translated_by_engine: dict[Engine, list[TranslationUnit]] = {}
        for i, (engine, translated_copy) in sorted(translated_copies.items()):
            cache_misses[i].translated_text = translated_copy.translated_text
            translated_by_engine.setdefault(engine, []).append(cache_misses[i])

        # Units left out by `_run_translate` keep the source file's value.
        for unit in cache_hits + [cache_misses[i] for i in sorted(translated_copies)]:
            unit.write_back(unit.translated_text)

        parse_result.save(destination_path)

        if self._translation_store is not None:
            for engine, translated_units in translated_by_engine.items():
                query_data = [
                    (unit.source_text, source_locale, target_locale, unit.translated_text) for unit in translated_units
                ]
                self._translation_store.store_batch(query_data, engine)

        return len(cache_misses) - len(translated_copies)
