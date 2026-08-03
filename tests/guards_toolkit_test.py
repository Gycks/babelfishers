from babelfishers.core.guards.toolkit import find_placeholders
from babelfishers.models.translation_resource import TranslationResourceType as T


class TestFindPlaceholdersRegexCategories:
    def test_finds_printf_style_placeholder_for_json_resource_type(self):
        spans = find_placeholders("Found %d results for %s", T.JSON)
        assert [s.matched_text for s in spans] == ["%d", "%s"]

    def test_finds_positional_printf_placeholder(self):
        spans = find_placeholders("Hello %1$s, you have %2$d messages", T.JSON)
        assert [s.matched_text for s in spans] == ["%1$s", "%2$d"]

    def test_finds_rails_named_placeholder_for_yaml_resource_type(self):
        spans = find_placeholders("Hello %{name}", T.YAML)
        assert [s.matched_text for s in spans] == ["%{name}"]

    def test_finds_symfony_percent_placeholder_for_yaml_resource_type(self):
        spans = find_placeholders("Hello %name%", T.YAML)
        assert [s.matched_text for s in spans] == ["%name%"]

    def test_finds_python_percent_named_placeholder_for_gettext_resource_type(self):
        spans = find_placeholders("You have %(count)d items", T.GETTEXT)
        assert [s.matched_text for s in spans] == ["%(count)d"]

    def test_html_resource_type_has_no_regex_categories_only_brace_scan(self):
        spans = find_placeholders("Found %d results", T.HTML)
        assert spans == []

    def test_yaml_resource_type_does_not_match_printf_style(self):
        spans = find_placeholders("Found %d results", T.YAML)
        assert spans == []


class TestFindPlaceholdersIcuBraceScan:
    def test_finds_balanced_icu_brace_placeholder(self):
        spans = find_placeholders("Hello {name}", T.HTML)
        assert [s.matched_text for s in spans] == ["{name}"]

    def test_nested_icu_braces_captured_as_single_balanced_span(self):
        text = "{count, plural, one {# item} other {# items}}"
        spans = find_placeholders(text, T.HTML)
        assert [s.matched_text for s in spans] == [text]

    def test_stray_unmatched_closing_brace_is_ignored(self):
        spans = find_placeholders("a } b {c} d", T.HTML)
        assert [s.matched_text for s in spans] == ["{c}"]

    def test_apostrophe_in_contraction_does_not_suppress_following_placeholder(self):
        spans = find_placeholders("It's your turn: {name}", T.HTML)
        assert [s.matched_text for s in spans] == ["{name}"]

    def test_apostrophe_in_possessive_does_not_suppress_following_placeholder(self):
        spans = find_placeholders("User's items: {count}", T.HTML)
        assert [s.matched_text for s in spans] == ["{count}"]

    def test_apostrophe_in_contraction_before_multiple_placeholders(self):
        spans = find_placeholders("Don't miss {event} on {date}", T.HTML)
        assert [s.matched_text for s in spans] == ["{event}", "{date}"]

    def test_literal_brace_escaped_with_icu_quoting_is_not_treated_as_placeholder(self):
        text = "{count, plural, one {'{'} other {#}}"
        spans = find_placeholders(text, T.HTML)
        assert [s.matched_text for s in spans] == [text]


class TestFindPlaceholdersPrecedenceAndOrdering:
    def test_regex_match_takes_precedence_over_overlapping_brace_match(self):
        spans = find_placeholders("Hello %{name}, welcome", T.YAML)
        assert len(spans) == 1
        assert spans[0].matched_text == "%{name}"
        assert spans[0].category != "brace_icu"

    def test_matches_sorted_by_start_position_not_discovery_order(self):
        spans = find_placeholders("{first} then %s then {second}", T.JSON)
        assert [s.matched_text for s in spans] == ["{first}", "%s", "{second}"]

    def test_returns_empty_list_for_text_with_no_placeholders(self):
        assert find_placeholders("Just plain text", T.JSON) == []

    def test_returns_empty_list_for_empty_text(self):
        assert find_placeholders("", T.JSON) == []
