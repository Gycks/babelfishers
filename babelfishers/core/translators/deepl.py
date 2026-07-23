import deepl

from babelfishers.core.translators.translator import Translator
from babelfishers.core.translators.translator_factory import register
from babelfishers.models.engine import Engine
from babelfishers.models.translations import TranslationUnit
from babelfishers.utils.utils import get_env


@register(Engine.DeepL)
class DeeplTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Engine.DeepL)
        self._translator: deepl.DeepLClient = deepl.DeepLClient(get_env("DEEPL_API_KEY"))

    def translate(self, data: list[TranslationUnit], source: str, target: str) -> list[TranslationUnit]:
        pass
