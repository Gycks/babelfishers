from enum import StrEnum
from typing import Self


class Engine(StrEnum):
    DeepL = "deepl"
    Azure = "azure"
    Anthropic = "anthropic"
    OpenAI = "openai"
    GoogleTranslate = "google-translate"
    LibreTranslate = "libre-translate"

    @classmethod
    def validate(cls, name: str) -> Self | None:
        try:
            return Engine(name.lower().strip())

        except ValueError:
            return None
