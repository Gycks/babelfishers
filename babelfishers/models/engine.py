from enum import StrEnum
from typing import Self


class Engine(StrEnum):
    DeepL = "deepl"
    Azure = "azure"
    Anthropic = "anthropic"
    OpenAI = "open-ai"
    GoogleTranslate = "google-translate"
    LibreTranslate = "libre-translate"

    @classmethod
    def validate(cls, name: str) -> Self | None:
        try:
            return Engine(name)

        except ValueError:
            return None
