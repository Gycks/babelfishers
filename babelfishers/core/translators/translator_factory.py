from collections.abc import Callable

from babelfishers.core.translators.translator import Translator
from babelfishers.models.engine import Engine


_registry: dict[Engine, type] = {}


def register(engine_type: Engine) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _registry[engine_type] = cls
        return cls

    return decorator


class TranslatorFactory:
    @staticmethod
    def create(engine_type: Engine) -> Translator:
        """
        Creates a translator instance for the specified engine.

        Args:
            engine_type: The translation engine to instantiate.

        Returns:
            An instance of the translator associated with engine type.
        """

        cls = _registry.get(engine_type)
        if cls is None:
            raise ValueError(f"No class registered for {engine_type}")

        translator = cls()
        if not isinstance(translator, Translator):
            raise ValueError(f"Invalid translator: {engine_type}")

        return translator
