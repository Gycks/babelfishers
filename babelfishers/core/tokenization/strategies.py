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

    def make_token(self, index: int, namespace: str) -> str:
        return f"{namespace}{index}"

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        return f'<{self.tag} id="{token}">{replacement}</{self.tag}>'

    def restore_text(self, text: str, token: str, replacement: str) -> str:
        pattern = re.compile(
            rf'<{self.tag}[^>]*id="{re.escape(token)}"[^>]*>(.*?)</{self.tag}>',
            re.DOTALL,
        )
        text, n = pattern.subn(replacement, text)
        if n:
            return text
        # tag got mangled but the bare token id survived somewhere
        return text.replace(token, replacement)

    def leftover_pattern(self, token: str) -> re.Pattern[str]:
        return re.compile(rf'<{self.tag}[^>]*id="{re.escape(token)}"')


class XmlIgnoreTagStrategy(_WrapperTagStrategy):
    tag = "gls"


class NoTranslateSpanStrategy(_WrapperTagStrategy):
    tag = "span"

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        return f'<span translate="no" id="{token}">{replacement}</span>'


class InstructionTagStrategy(_WrapperTagStrategy):
    tag = "gls"


class DictionaryMarkupStrategy(TokenStrategy):
    needs_restore = False

    def make_token(self, index: int, namespace: str) -> str:
        return f"{namespace}{index}"

    def build_span(self, token: str, source_term: str, replacement: str) -> str:
        safe_source = source_term.replace('"', "&quot;")
        safe_repl = replacement.replace('"', "&quot;")
        return f'<mstrans:dictionary translation="{safe_repl}">{safe_source}</mstrans:dictionary>'

    def leftover_pattern(self, token: str) -> re.Pattern[str]:
        return re.compile(r"<mstrans:dictionary\b")
