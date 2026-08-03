from babelfishers.core.guards.placeholder_guard import PlaceholderGuard
from babelfishers.models.engine import Engine
from babelfishers.models.translation_resource import TranslationResourceType as T
from babelfishers.models.translations import TranslationUnit


def _noop_write_back(_: str) -> None:
    pass


def _unit(key: str, source_text: str, unit_type: T = T.JSON) -> TranslationUnit:
    return TranslationUnit(unit_type=unit_type, key=key, source_text=source_text, write_back=_noop_write_back)


class TestPlaceholderGuardProtect:
    def test_wraps_placeholder_using_engine_strategy(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Hello %s")])

        assert protected[0].source_text == 'Hello <gls id="ph0">%s</gls>'

    def test_leaves_units_without_placeholders_unchanged(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Plain text")])

        assert protected[0].source_text == "Plain text"

    def test_does_not_mutate_the_input_list_or_its_units(self):
        guard = PlaceholderGuard(Engine.DeepL)
        original = [_unit("k1", "Hello %s")]
        protected = guard.protect(original)

        assert protected[0] is not original[0]
        assert original[0].source_text == "Hello %s"

    def test_wraps_multiple_placeholders_without_offset_corruption(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Found %d results for %s")])

        assert protected[0].source_text == 'Found <gls id="ph1">%d</gls> results for <gls id="ph0">%s</gls>'

    def test_resource_type_specific_categories_apply_per_unit(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([
            _unit("k1", "Hello %{name}", unit_type=T.YAML),
            _unit("k2", "Hello %{name}", unit_type=T.JSON),
        ])

        assert protected[0].source_text == 'Hello <gls id="ph0">%{name}</gls>'
        assert protected[1].source_text == 'Hello %<gls id="ph0">{name}</gls>'


class TestPlaceholderGuardRestore:
    def test_restores_cleanly_when_translator_echoes_wrapped_tag_verbatim(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Hello %s")])
        protected[0].translated_text = protected[0].source_text

        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text == "Hello %s"

    def test_reports_not_clean_when_tag_survives_mangled(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Hello %s")])
        protected[0].translated_text = 'Bonjour <gls foo="bar" id="ph0">broken'

        all_clean = guard.restore(protected)

        assert all_clean is False
        assert protected[0].translated_text == 'Bonjour <gls foo="bar" id="ph0">broken'

    def test_reports_not_clean_when_a_needs_restore_false_strategy_tag_survives_untouched(self):
        """
        Engines like Azure resolve their dictionary tag natively and never have
        restore_text() run over it (needs_restore=False) — restore() just checks
        whether the tag is still present in the translated output.
        """
        guard = PlaceholderGuard(Engine.Azure)
        protected = guard.protect([_unit("k1", "Hello %s")])
        protected[0].translated_text = protected[0].source_text

        all_clean = guard.restore(protected)

        assert all_clean is False
        assert protected[0].translated_text == protected[0].source_text

    def test_skips_restoration_for_unit_with_no_recorded_placeholders(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Plain text")])
        protected[0].translated_text = "Texte simple"

        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text == "Texte simple"

    def test_skips_restoration_when_translated_text_is_none(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Hello %s")])
        protected[0].translated_text = None

        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text is None

    def test_attempts_restoration_when_translated_text_is_empty_string(self):
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Hello %s")])
        protected[0].translated_text = ""

        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text == ""

    def test_restore_keeps_the_token_map_so_a_retry_can_reuse_the_same_guard_instance(self):
        """
        PlaceholderGuard is created once per engine and reused across retry
        attempts within that engine (see TranslationPipeline._run_translate).
        restore() must not consume its own tracking state on the first call,
        or a second attempt using the same instance would have nothing left
        to restore against and would silently ship the wrapper tag unresolved.
        """
        guard = PlaceholderGuard(Engine.DeepL)
        protected = guard.protect([_unit("k1", "Hello %s")])
        protected[0].translated_text = protected[0].source_text
        guard.restore(protected)

        assert guard._token_maps.get("k1") is not None

        # a second restore() call against the same guard instance still works
        protected[0].translated_text = protected[0].source_text
        all_clean = guard.restore(protected)

        assert all_clean is True
        assert protected[0].translated_text == "Hello %s"
