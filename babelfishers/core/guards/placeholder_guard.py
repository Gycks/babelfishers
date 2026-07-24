from copy import deepcopy

from babelfishers.core.guards.guard import ProtectionGuard
from babelfishers.core.guards.toolkit import find_placeholders
from babelfishers.models.engine import Engine
from babelfishers.models.guards import ProtectedEntry
from babelfishers.models.translations import TranslationUnit


class PlaceholderGuard(ProtectionGuard):
    def __init__(self, engine: Engine) -> None:
        super().__init__(engine, "ph")

    def protect(self, data: list[TranslationUnit]) -> list[TranslationUnit]:
        data_copy = deepcopy(data)
        for unit in data_copy:
            spans = find_placeholders(unit.source_text, unit.unit_type)
            if not spans:
                continue

            entries: list[ProtectedEntry] = []
            text = unit.source_text

            for i, span in enumerate(reversed(spans)):
                token = self._strategy.make_token(i, self._namespace)
                original = span.matched_text
                wrapped = self._strategy.build_span(token, original, original)
                entries.append(ProtectedEntry(token=token, replacement=original))
                text = text[: span.start] + wrapped + text[span.end :]

            if entries:
                self._token_maps[unit.key] = entries
                unit.source_text = text

        return data_copy
