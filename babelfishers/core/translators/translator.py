from abc import ABC, abstractmethod

from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit


class Translator(ABC):
    def __init__(self, engine: Engine) -> None:
        self._engine: Engine = engine
        self._MAX_RATE_LIMIT_RETRIES: int = 3
        self._RATE_LIMIT_BASE_DELAY_SECONDS: float = 2.0

    @property
    def engine(self) -> Engine:
        return self._engine

    @abstractmethod
    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        """
        Translate the given translation units.

        Sets `translated_text` on each unit. The translation pipeline restores protected
        spans, checks the result and writes it back, so a translator never calls `write_back`.

        Args:
            data: Translation units to translate.
            source: The source language.
            target: The target language.

        Returns:
            The translated translation units in the same order as the input.
        """
        raise NotImplementedError("The abstract method 'translate()' must be implemented by subclasses.")
