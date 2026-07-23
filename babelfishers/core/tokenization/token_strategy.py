import re
from abc import ABC, abstractmethod


class TokenStrategy(ABC):
    """
    Controls how a protected text span is embedded into the source text
    before translation, and how it's resolved after.
    """

    needs_restore: bool = True

    @abstractmethod
    def make_token(self, index: int) -> str:
        """A short, unique id for this span, scoped to one unit."""

    @abstractmethod
    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        """Text spliced into source_text in place of the matched term."""

    def restore_text(self, text: str, token: str, replacement: str) -> str:
        return text.replace(token, replacement)

    def leftover_pattern(self, token: str) -> re.Pattern[str]:
        return re.compile(re.escape(token))
