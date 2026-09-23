import re
from secrets import token_hex

from babelfishers.core.tokenization.token_strategy import TokenStrategy


class DefaultMaskStrategy(TokenStrategy):
    def make_token(self, index: int, namespace: str) -> str:
        return f"zz{namespace}{token_hex(4)}zz{index}zz"

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        return token

    def leftover_pattern(self, token: str) -> re.Pattern[str]:
        return re.compile(re.escape(token), re.IGNORECASE)


class _WrapperTagStrategy(TokenStrategy):
    tag = "gls"

    @property
    def ignore_tag_names(self) -> list[str]:
        return [self.tag]

    @property
    def ignore_tag_shapes(self) -> list[str]:
        return [f"<{self.tag} id=...>content</{self.tag}>"]

    def make_token(self, index: int, namespace: str) -> str:
        return f"{namespace}{index}"

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        return f'<{self.tag} id="{token}">{replacement}</{self.tag}>'

    def restore_text(self, text: str, token: str, replacement: str) -> str:
        pattern = re.compile(
            rf'<{self.tag}[^>]*id="{re.escape(token)}"[^>]*>(.*?)</{self.tag}>',
            re.DOTALL,
        )
        return pattern.sub(replacement, text)

    def leftover_pattern(self, token: str) -> re.Pattern[str]:
        return re.compile(rf'<{self.tag}[^>]*id="{re.escape(token)}"')


class XmlIgnoreTagStrategy(_WrapperTagStrategy):
    tag = "gls"


class NoTranslateSpanStrategy(_WrapperTagStrategy):
    tag = "span"

    @property
    def ignore_tag_shapes(self) -> list[str]:
        return [f'<{self.tag} translate="no" id=...>content</{self.tag}>']

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        return f'<span translate="no" id="{token}">{replacement}</span>'


class InstructionTagStrategy(_WrapperTagStrategy):
    tag = "gls"


class DictionaryMarkupStrategy(TokenStrategy):
    needs_restore = False
    tag = "mstrans:dictionary"

    @property
    def ignore_tag_names(self) -> list[str]:
        return [self.tag]

    @property
    def ignore_tag_shapes(self) -> list[str]:
        return [f'<{self.tag} translation="...">source</{self.tag}>']

    def make_token(self, index: int, namespace: str) -> str:
        return f"{namespace}{index}"

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        safe_source = source_term.replace('"', "&quot;")
        safe_repl = replacement.replace('"', "&quot;")
        return f'<{self.tag} translation="{safe_repl}">{safe_source}</{self.tag}>'

    def leftover_pattern(self, token: str) -> re.Pattern[str]:
        return re.compile(rf"<{re.escape(self.tag)}\b")
