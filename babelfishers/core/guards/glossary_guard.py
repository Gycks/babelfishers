from copy import deepcopy

from babelfishers.core.guards.guard import ProtectionGuard
from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.tokenization.token_strategy import TokenStrategy
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary, GlossaryTerm
from babelfishers.models.guards import ProtectedEntry
from babelfishers.models.translations import TranslationUnit


class GlossaryGuard(ProtectionGuard):
    def __init__(self, glossary: Glossary, target_locale: str, engine: Engine) -> None:
        self._glossary: Glossary = glossary
        self._target_locale: str = target_locale
        self._strategy: TokenStrategy = TokenStrategyFactory.get_strategy_for(engine)
        self._token_maps: dict[str, list[ProtectedEntry]] = {}

    def _resolve(self, term: GlossaryTerm) -> str:
        return term.translations.get(self._target_locale) or term.term

    def protect(self, data: list[TranslationUnit]) -> list[TranslationUnit]:
        data_copy = deepcopy(data)
        for unit in data_copy:
            glossary_term = self._glossary.lookup(unit.source_text)

            if glossary_term:
                if glossary_term.translatable:
                    unit.context_hint = glossary_term.context
                else:
                    unit.translated_text = self._resolve(glossary_term)
                    unit.skip_translation = True
                continue

            matches = self._glossary.find_matches(unit.source_text)
            if not matches:
                continue

            entries: list[ProtectedEntry] = []
            hints: list[str] = []
            text = unit.source_text

            for i, match in enumerate(reversed(matches)):
                if match.term.translatable:
                    hints.append(match.term.context)
                    continue

                token = self._strategy.make_token(i)
                replacement = self._resolve(match.term)
                span = self._strategy.build_span(token, match.matched_text, replacement)

                entries.append(ProtectedEntry(token=token, replacement=replacement))
                text = text[: match.start] + span + text[match.end:]

            if hints:
                existing = f"{unit.context_hint}\n" if unit.context_hint else ""
                unit.context_hint = existing + "\n".join(reversed(hints))

            if entries:
                self._token_maps[unit.key] = entries

            unit.source_text = text
        return data_copy

    def restore(self, data: list[TranslationUnit]) -> bool:
        success = True
        for unit in data:
            entries = self._token_maps.pop(unit.key, None)
            if not entries or unit.translated_text is None:
                continue

            text = unit.translated_text
            if self._strategy.needs_restore:
                for entry in entries:
                    text = self._strategy.restore_text(text, entry.token, entry.replacement)

            for entry in entries:
                if self._strategy.leftover_pattern(entry.token).search(text):
                    success = False

            unit.translated_text = text
        return success
