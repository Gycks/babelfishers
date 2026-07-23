from babelfishers.core.tokenization.strategies import (
    DefaultMaskStrategy,
    DictionaryMarkupStrategy,
    InstructionTagStrategy,
    NoTranslateSpanStrategy,
    XmlIgnoreTagStrategy,
)
from babelfishers.core.tokenization.token_strategy import TokenStrategy
from babelfishers.models.engine import Engine


class TokenStrategyFactory:
    _ENGINE_STRATEGIES: dict[Engine, type[TokenStrategy]] = {
        Engine.DeepL: XmlIgnoreTagStrategy,
        Engine.Azure: DictionaryMarkupStrategy,
        Engine.GoogleTranslate: NoTranslateSpanStrategy,
        Engine.Anthropic: InstructionTagStrategy,
        Engine.OpenAI: InstructionTagStrategy,
        Engine.LibreTranslate: DefaultMaskStrategy,
    }

    @classmethod
    def get_strategy_for(cls, engine: Engine) -> TokenStrategy:
        """
        Provides the tokenization strategy associated with the
        provided engine.

        Args:
            engine: The engine

        Returns:
            The tokenization strategy
        """
        return cls._ENGINE_STRATEGIES.get(engine, DefaultMaskStrategy)()
