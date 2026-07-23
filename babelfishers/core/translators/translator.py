from abc import ABC, abstractmethod

from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit


class Translator(ABC):
    def __init__(self, engine: Engine) -> None:
        self._engine: Engine = engine

    @property
    def engine(self) -> Engine:
        return self._engine

    @abstractmethod
    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        """
        Translate the given translation units.

        Args:
            data: Translation units to translate.
            source: The source language.
            target: The target language.

        Returns:
            The translated translation units in the same order as the input.
        """
        raise NotImplementedError("The abstract method 'translate()' must be implemented by subclasses.")
