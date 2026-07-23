from abc import ABC, abstractmethod

from babelfishers.models.translations import TranslationUnit


class ProtectionGuard(ABC):
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

    @abstractmethod
    def restore(self, data: list[TranslationUnit]) -> bool:
        """
        Restore protected translation units content after translation.

        NOTE: The translation units are mutated in-place.

        Args:
            data: Translation units whose protected content should be restored.

        Return:
            True, if the process was successful.
        """
        raise NotImplementedError("The abstract method 'restore()' must be implemented by subclasses.")
