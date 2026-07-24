from copy import deepcopy

from babelfishers.core.guards.guard import ProtectionGuard
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary, GlossaryTerm
from babelfishers.models.guards import ProtectedEntry
from babelfishers.models.translations import TranslationUnit


class GlossaryGuard(ProtectionGuard):
    def __init__(self, glossary: Glossary, target_locale: str, engine: Engine) -> None:
        super().__init__(engine, "gh")
        self._glossary: Glossary = glossary
        self._target_locale: str = target_locale

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

                token = self._strategy.make_token(i, self._namespace)
                replacement = self._resolve(match.term)
                span = self._strategy.build_span(token, match.matched_text, replacement)

                entries.append(ProtectedEntry(token=token, replacement=replacement))
                text = text[: match.start] + span + text[match.end :]

            if hints:
                existing = f"{unit.context_hint}\n" if unit.context_hint else ""
                unit.context_hint = existing + "\n".join(reversed(hints))

            if entries:
                self._token_maps[unit.key] = entries

            unit.source_text = text
        return data_copy
