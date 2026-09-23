from babelfishers.core.tokenization.factory import TokenStrategyFactory
from babelfishers.core.tokenization.strategies import (
    DefaultMaskStrategy,
    DictionaryMarkupStrategy,
    InstructionTagStrategy,
    NoTranslateSpanStrategy,
    XmlIgnoreTagStrategy,
)
from babelfishers.models.engine import Engine


class TestDefaultMaskStrategy:
    def test_make_token_embeds_namespace_and_index(self):
        strategy = DefaultMaskStrategy()
        token = strategy.make_token(3, "ph")
        assert token.startswith("zzph")
        assert token.endswith("zz3zz")

    def test_make_token_is_unique_across_calls(self):
        strategy = DefaultMaskStrategy()
        tokens = {strategy.make_token(0, "ph") for _ in range(20)}
        assert len(tokens) == 20

    def test_build_span_returns_bare_token(self):
        strategy = DefaultMaskStrategy()
        token = strategy.make_token(0, "ph")
        assert strategy.build_span(token, "%s", "%s") == token

    def test_needs_restore_defaults_to_true(self):
        assert DefaultMaskStrategy().needs_restore is True

    def test_restore_text_replaces_token_with_replacement(self):
        strategy = DefaultMaskStrategy()
        token = strategy.make_token(0, "ph")
        text = f"Bonjour {token} maintenant"
        assert strategy.restore_text(text, token, "%s") == "Bonjour %s maintenant"

    def test_leftover_pattern_is_case_insensitive(self):
        strategy = DefaultMaskStrategy()
        token = strategy.make_token(0, "ph")
        assert strategy.leftover_pattern(token).search(token.upper()) is not None


class TestXmlIgnoreTagStrategy:
    def test_build_span_wraps_replacement_in_gls_tag_with_token_id(self):
        strategy = XmlIgnoreTagStrategy()
        span = strategy.build_span("gh0", "Widget", "Gadget")
        assert span == '<gls id="gh0">Gadget</gls>'

    def test_restore_text_extracts_replacement_from_clean_tag(self):
        strategy = XmlIgnoreTagStrategy()
        text = 'Bonjour, <gls id="gh0">Gadget</gls> maintenant'
        assert strategy.restore_text(text, "gh0", "Gadget") == "Bonjour, Gadget maintenant"

    def test_restore_text_leaves_text_untouched_when_tag_is_mangled(self):
        """
        A blind bare-token replace here would erase the marker leftover_pattern
        needs to detect the failure, so a mangled tag must be left as-is instead
        of "repaired" by guesswork.
        """
        strategy = XmlIgnoreTagStrategy()
        text = 'Bonjour, <gls foo="bar" id="gh0">broken'
        assert strategy.restore_text(text, "gh0", "Gadget") == text

    def test_restore_text_is_a_no_op_when_token_fully_disappears(self):
        strategy = XmlIgnoreTagStrategy()
        text = "Bonjour, maintenant"
        assert strategy.restore_text(text, "gh0", "Gadget") == text

    def test_leftover_pattern_detects_surviving_tag_opening(self):
        strategy = XmlIgnoreTagStrategy()
        text = '<gls foo="bar" id="gh0">broken'
        assert strategy.leftover_pattern("gh0").search(text) is not None

    def test_leftover_pattern_does_not_detect_a_fully_restored_text(self):
        strategy = XmlIgnoreTagStrategy()
        assert strategy.leftover_pattern("gh0").search("Bonjour, Gadget maintenant") is None

    def test_needs_restore_defaults_to_true(self):
        assert XmlIgnoreTagStrategy().needs_restore is True


class TestNoTranslateSpanStrategy:
    def test_build_span_uses_translate_no_span(self):
        strategy = NoTranslateSpanStrategy()
        span = strategy.build_span("gh0", "Widget", "Gadget")
        assert span == '<span translate="no" id="gh0">Gadget</span>'

    def test_restore_text_extracts_replacement_from_clean_span(self):
        strategy = NoTranslateSpanStrategy()
        text = 'Bonjour, <span translate="no" id="gh0">Gadget</span> maintenant'
        assert strategy.restore_text(text, "gh0", "Gadget") == "Bonjour, Gadget maintenant"


class TestInstructionTagStrategy:
    def test_build_span_wraps_replacement_in_gls_tag(self):
        strategy = InstructionTagStrategy()
        span = strategy.build_span("gh0", "Widget", "Gadget")
        assert span == '<gls id="gh0">Gadget</gls>'


class TestDictionaryMarkupStrategy:
    def test_needs_restore_is_false(self):
        assert DictionaryMarkupStrategy().needs_restore is False

    def test_build_span_embeds_source_and_translation_attributes(self):
        strategy = DictionaryMarkupStrategy()
        span = strategy.build_span("gh0", "Widget", "Gadget")
        assert span == '<mstrans:dictionary translation="Gadget">Widget</mstrans:dictionary>'

    def test_build_span_escapes_embedded_double_quotes(self):
        strategy = DictionaryMarkupStrategy()
        span = strategy.build_span("gh0", 'Say "hi"', 'Dis "salut"')
        assert span == '<mstrans:dictionary translation="Dis &quot;salut&quot;">Say &quot;hi&quot;</mstrans:dictionary>'

    def test_leftover_pattern_detects_unconsumed_dictionary_tag(self):
        strategy = DictionaryMarkupStrategy()
        span = strategy.build_span("gh0", "Widget", "Gadget")
        assert strategy.leftover_pattern("gh0").search(span) is not None

    def test_leftover_pattern_does_not_detect_plain_translated_text(self):
        strategy = DictionaryMarkupStrategy()
        assert strategy.leftover_pattern("gh0").search("Dis salut") is None


class TestTokenStrategyFactory:
    def test_deepl_uses_xml_ignore_tag_strategy(self):
        assert isinstance(TokenStrategyFactory.get_strategy_for(Engine.DeepL), XmlIgnoreTagStrategy)

    def test_azure_uses_dictionary_markup_strategy(self):
        assert isinstance(TokenStrategyFactory.get_strategy_for(Engine.Azure), DictionaryMarkupStrategy)

    def test_google_translate_uses_no_translate_span_strategy(self):
        assert isinstance(TokenStrategyFactory.get_strategy_for(Engine.GoogleTranslate), NoTranslateSpanStrategy)

    def test_anthropic_uses_instruction_tag_strategy(self):
        assert isinstance(TokenStrategyFactory.get_strategy_for(Engine.Anthropic), InstructionTagStrategy)

    def test_openai_uses_instruction_tag_strategy(self):
        assert isinstance(TokenStrategyFactory.get_strategy_for(Engine.OpenAI), InstructionTagStrategy)

    def test_libre_translate_uses_default_mask_strategy(self):
        assert isinstance(TokenStrategyFactory.get_strategy_for(Engine.LibreTranslate), DefaultMaskStrategy)

    def test_each_call_returns_a_fresh_strategy_instance(self):
        first = TokenStrategyFactory.get_strategy_for(Engine.DeepL)
        second = TokenStrategyFactory.get_strategy_for(Engine.DeepL)
        assert first is not second
