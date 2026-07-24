from abc import ABC, abstractmethod

from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.tokenization.token_strategy import TokenStrategy
from babelfishers.models.engine import Engine
from babelfishers.models.guards import ProtectedEntry
from babelfishers.models.translations import TranslationUnit


class ProtectionGuard(ABC):
    def __init__(self, engine: Engine, namespace: str) -> None:
        self._namespace: str = namespace
        self._strategy: TokenStrategy = TokenStrategyFactory.get_strategy_for(engine)
        self._token_maps: dict[str, list[ProtectedEntry]] = {}

    """
    Abstract interface for protecting and restoring translation data.

    A ProtectionGuard defines the contract for components that temporarily
    protect sensitive or non-translatable content in translation units before
    processing and restore the original content afterward.
    """

    @abstractmethod
    def protect(self, data: list[TranslationUnit]) -> list[TranslationUnit]:
        """
        Protect translation units content before translation.

        Args:
            data: Translation units whose content should be protected.

        Returns:
            A new copy of the translation unit with the protection schema applied
        """
        raise NotImplementedError("The abstract method 'protect()' must be implemented by subclasses.")

    def restore(self, data: list[TranslationUnit]) -> bool:
        """
        Restore protected translation units content after translation.

        NOTE: The translation units are mutated in-place.

        Args:
            data: Translation units whose protected content should be restored.

        Return:
            True, if the process was successful.
        """
        all_clean = True
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
                    all_clean = False

            unit.translated_text = text
        return all_clean
