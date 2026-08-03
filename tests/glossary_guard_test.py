from babelfishers.core.guards.glossary_guard import GlossaryGuard
from babelfishers.models.engine import Engine
from babelfishers.models.glossary import Glossary, GlossaryTerm
from babelfishers.models.translation_resource import TranslationResourceType as T
from babelfishers.models.translations import TranslationUnit


def _noop_write_back(_: str) -> None:
    pass


def _unit(key: str, source_text: str) -> TranslationUnit:
    return TranslationUnit(unit_type=T.JSON, key=key, source_text=source_text, write_back=_noop_write_back)


def _guard(terms: list[GlossaryTerm], target_locale: str = "fr") -> GlossaryGuard:
    return GlossaryGuard(Glossary(terms=terms), target_locale, Engine.DeepL)


class TestGlossaryGuardProtectExactMatch:
    def test_exact_match_non_translatable_sets_translated_text_and_skips_translation(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])
        protected = guard.protect([_unit("k1", "Widget")])

        assert protected[0].translated_text == "Gadget"
        assert protected[0].skip_translation is True
        assert protected[0].source_text == "Widget"

    def test_exact_match_non_translatable_falls_back_to_term_when_no_translation_for_locale(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        protected = guard.protect([_unit("k1", "Widget")])

        assert protected[0].translated_text == "Widget"
        assert protected[0].skip_translation is True

    def test_exact_match_translatable_sets_context_hint_and_leaves_text_untouched(self):
        guard = _guard([GlossaryTerm(term="Acme", translatable=True, context="brand, formal tone", translations={})])
        protected = guard.protect([_unit("k1", "Acme")])

        assert protected[0].context_hint == "brand, formal tone"
        assert protected[0].source_text == "Acme"
        assert protected[0].skip_translation is False
        assert protected[0].translated_text == ""


class TestGlossaryGuardProtectPartialMatch:
    def test_partial_match_non_translatable_wraps_term_with_replacement(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])
        protected = guard.protect([_unit("k1", "I bought a Widget yesterday")])

        assert protected[0].source_text == 'I bought a <gls id="gh0">Gadget</gls> yesterday'

    def test_partial_match_translatable_adds_hint_without_wrapping(self):
        guard = _guard([GlossaryTerm(term="Acme", translatable=True, context="brand, formal tone", translations={})])
        protected = guard.protect([_unit("k1", "Welcome to Acme today")])

        assert protected[0].source_text == "Welcome to Acme today"
        assert protected[0].context_hint == "brand, formal tone"

    def test_multiple_translatable_hints_accumulate_in_match_order(self):
        guard = _guard([
            GlossaryTerm(term="Acme", translatable=True, context="brand, formal tone", translations={}),
            GlossaryTerm(term="Zenith", translatable=True, context="product line, keep capitalized", translations={}),
        ])
        protected = guard.protect([_unit("k1", "Acme presents the new Zenith model")])

        assert protected[0].context_hint == "brand, formal tone\nproduct line, keep capitalized"

    def test_hints_are_appended_after_a_preexisting_context_hint(self):
        guard = _guard([GlossaryTerm(term="Acme", translatable=True, context="brand, formal tone", translations={})])
        unit = _unit("k1", "Welcome to Acme today")
        unit.context_hint = "preexisting hint"

        protected = guard.protect([unit])

        assert protected[0].context_hint == "preexisting hint\nbrand, formal tone"

    def test_partial_match_non_translatable_falls_back_to_term_when_no_translation_for_locale(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        protected = guard.protect([_unit("k1", "I bought a Widget yesterday")])

        assert protected[0].source_text == 'I bought a <gls id="gh0">Widget</gls> yesterday'

    def test_unit_with_no_glossary_matches_passes_through_unchanged(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        protected = guard.protect([_unit("k1", "nothing special here")])

        assert protected[0].source_text == "nothing special here"
        assert protected[0].context_hint is None


class TestGlossaryGuardRestore:
    def test_restore_leaves_exact_match_skip_translation_unit_untouched(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])
        protected = guard.protect([_unit("k1", "Widget")])
        protected[0].translated_text = "something a translator returned"

        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text == "something a translator returned"

    def test_restore_round_trips_a_partial_match_when_tag_survives_translation(self):
        guard = _guard([GlossaryTerm(term="Widget", translatable=False, context="", translations={"fr": "Gadget"})])
        protected = guard.protect([_unit("k1", "I bought a Widget yesterday")])
        protected[0].translated_text = protected[0].source_text

        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text == "I bought a Gadget yesterday"
