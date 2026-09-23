import json
import logging
from pathlib import Path

import pytest

from babelfishers.models.glossary import Glossary, GlossaryTerm


@pytest.fixture
def write_glossary(tmp_path):
    def _write(entries: list[dict], filename: str = "glossary.json") -> Path:
        path = tmp_path / filename
        path.write_text(json.dumps(entries), encoding="utf-8")
        return path

    return _write


class TestGlossaryLoadFileValidation:
    def test_returns_none_when_file_path_is_none(self):
        assert Glossary.load(None) is None

    def test_raises_file_not_found_when_file_does_not_exist(self, tmp_path):
        missing_file = tmp_path / "non_existent.json"
        with pytest.raises(FileNotFoundError):
            Glossary.load(str(missing_file))

    @pytest.mark.parametrize("filename", [
        "glossary.txt",
        "glossary.yaml",
        "glossary.toml",
        "glossary",  # no extension at all
    ])
    def test_raises_value_error_when_file_extension_is_not_json(self, tmp_path, filename):
        invalid_file = tmp_path / filename
        invalid_file.write_text("[]")
        with pytest.raises(ValueError, match="JSON format"):
            Glossary.load(str(invalid_file))

    def test_accepts_json_extension_regardless_of_case(self, write_glossary):
        glossary_file = write_glossary([], filename="glossary.JSON")
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []


class TestGlossaryLoadEntryValidation:
    @pytest.fixture(autouse=True)
    def stub_supported_cultures(self, monkeypatch):
        monkeypatch.setattr(
            "babelfishers.models.glossary.SUPPORTED_CULTURES",
            {"en": "English", "fr": "French", "de": "German"},
        )

    def test_returns_empty_glossary_when_data_is_empty_list(self, write_glossary):
        glossary_file = write_glossary([])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []

    def test_skips_entry_missing_term_key(self, write_glossary, caplog):
        glossary_file = write_glossary([{"translations": {}}])
        with caplog.at_level(logging.WARNING):
            glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []
        assert any("'term' is missing" in r.message for r in caplog.records)

    @pytest.mark.parametrize("blank_term", ["", "   ", "\t\n"])
    def test_skips_entry_with_blank_or_whitespace_only_term(self, write_glossary, blank_term):
        glossary_file = write_glossary([{"term": blank_term, "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []

    def test_skips_entry_when_term_is_not_a_string(self, write_glossary, caplog):
        glossary_file = write_glossary([{"term": 123, "translations": {}}])
        with caplog.at_level(logging.WARNING):
            glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []
        assert any("not a string" in r.message for r in caplog.records)

    def test_translatable_defaults_to_false_when_missing(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget", "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].translatable is False

    def test_translatable_true_literal_is_preserved(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget", "translatable": True, "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].translatable is True

    def test_translatable_false_literal_is_preserved(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget", "translatable": False, "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].translatable is False

    @pytest.mark.parametrize("value,expected", [
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("1", True),
        ("false", False),
        ("FALSE", False),
        ("no", False),
        ("0", False),
        ("", False),
    ])
    def test_translatable_string_representations_are_interpreted_correctly(self, write_glossary, value, expected):
        glossary_file = write_glossary([{"term": "Widget", "translatable": value, "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].translatable is expected

    @pytest.mark.parametrize("invalid_value", ["maybe", "on", [1, 2, 3], {"a": 1}, 2, 3.5])
    def test_skips_entry_when_translatable_is_not_recognizable_as_a_boolean(self, write_glossary, caplog, invalid_value):
        glossary_file = write_glossary([{"term": "Widget", "translatable": invalid_value, "translations": {}}])
        with caplog.at_level(logging.WARNING):
            glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []
        assert any("not a valid boolean" in r.message for r in caplog.records)

    def test_context_defaults_to_empty_string_when_missing(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget", "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].context == ""

    def test_context_defaults_to_empty_string_when_explicitly_null(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget", "context": None, "translations": {}}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].context == ""

    def test_translations_defaults_to_empty_dict_when_missing(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget"}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].translations == {}

    def test_translations_defaults_to_empty_dict_when_explicitly_null(self, write_glossary):
        glossary_file = write_glossary([{"term": "Widget", "translations": None}])
        glossary = Glossary.load(str(glossary_file))
        assert glossary.terms[0].translations == {}

    def test_skips_entry_with_unsupported_translation_locale(self, write_glossary, caplog):
        glossary_file = write_glossary([{"term": "Widget", "translations": {"zz-ZZ": "Gadget"}}])
        with caplog.at_level(logging.WARNING):
            glossary = Glossary.load(str(glossary_file))
        assert glossary.terms == []
        assert any("unsupported language code" in r.message for r in caplog.records)

    def test_unsupported_locale_in_one_entry_does_not_affect_other_valid_entries(self, write_glossary):
        glossary_file = write_glossary([
            {"term": "ValidTerm", "translations": {}},
            {"term": "BadTerm", "translations": {"zz-ZZ": "x"}},
            {"term": "AnotherValidTerm", "translations": {"fr": "Autre"}},
        ])
        glossary = Glossary.load(str(glossary_file))
        loaded_terms = {t.term for t in glossary.terms}
        assert loaded_terms == {"ValidTerm", "AnotherValidTerm"}


class TestGlossaryIndexIsolation:
    def test_index_is_not_shared_between_glossary_instances(self):
        a = Glossary(terms=[GlossaryTerm(term="A", translatable=False, context="", translations={})])
        b = Glossary(terms=[GlossaryTerm(term="B", translatable=False, context="", translations={})])

        assert a.lookup("A") is not None
        assert a.lookup("B") is None
        assert b.lookup("B") is not None
        assert b.lookup("A") is None


class TestGlossaryLookup:
    def test_lookup_is_case_insensitive(self):
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        assert glossary.lookup("WIDGET") is not None
        assert glossary.lookup("widget") is not None

    def test_lookup_strips_leading_and_trailing_whitespace(self):
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        assert glossary.lookup("  Widget  ") is not None

    def test_lookup_returns_none_for_unknown_term(self):
        glossary = Glossary(terms=[])
        assert glossary.lookup("Anything") is None

    def test_lookup_does_not_normalize_internal_whitespace(self):
        glossary = Glossary(terms=[GlossaryTerm(term="New York", translatable=False, context="", translations={})])
        assert glossary.lookup("New York") is not None
        assert glossary.lookup("New  York") is None

    def test_last_duplicate_term_wins_when_two_entries_normalize_to_the_same_key(self):
        glossary = Glossary(terms=[
            GlossaryTerm(term="Widget", translatable=False, context="first", translations={}),
            GlossaryTerm(term="WIDGET", translatable=True, context="second", translations={}),
        ])
        result = glossary.lookup("widget")
        assert result.context == "second"


class TestGlossaryFindMatches:
    def test_finds_single_term_match(self):
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        matches = glossary.find_matches("I bought a Widget yesterday")
        assert len(matches) == 1
        assert matches[0].matched_text == "Widget"

    def test_matching_is_case_insensitive(self):
        glossary = Glossary(terms=[GlossaryTerm(term="widget", translatable=False, context="", translations={})])
        matches = glossary.find_matches("I bought a WIDGET yesterday")
        assert len(matches) == 1
        assert matches[0].matched_text == "WIDGET"

    def test_does_not_match_substring_within_a_larger_word(self):
        glossary = Glossary(terms=[GlossaryTerm(term="cat", translatable=False, context="", translations={})])
        matches = glossary.find_matches("The category is broad")
        assert matches == []

    def test_returns_no_matches_for_empty_text(self):
        glossary = Glossary(terms=[GlossaryTerm(term="Widget", translatable=False, context="", translations={})])
        assert glossary.find_matches("") == []

    def test_returns_no_matches_when_no_terms_defined(self):
        glossary = Glossary(terms=[])
        assert glossary.find_matches("Widgets everywhere") == []

    def test_longer_term_takes_precedence_over_shorter_overlapping_term(self):
        glossary = Glossary(terms=[
            GlossaryTerm(term="New York", translatable=False, context="", translations={}),
            GlossaryTerm(term="York", translatable=False, context="", translations={}),
        ])
        matches = glossary.find_matches("I live in New York")
        assert len(matches) == 1
        assert matches[0].matched_text == "New York"

    def test_matches_are_sorted_by_start_position_not_term_length(self):
        glossary = Glossary(terms=[
            GlossaryTerm(term="Gadget", translatable=False, context="", translations={}),
            GlossaryTerm(term="Widget", translatable=False, context="", translations={}),
        ])
        matches = glossary.find_matches("Widget then later Gadget")
        assert [m.matched_text for m in matches] == ["Widget", "Gadget"]

    def test_multi_word_term_with_internal_space_matches_correctly(self):
        glossary = Glossary(terms=[GlossaryTerm(term="New York", translatable=False, context="", translations={})])
        matches = glossary.find_matches("I live in New York City")
        assert len(matches) == 1
        assert matches[0].matched_text == "New York"

    def test_hyphenated_term_matches_correctly(self):
        glossary = Glossary(terms=[GlossaryTerm(term="state-of-the-art", translatable=False, context="", translations={})])
        matches = glossary.find_matches("This is a state-of-the-art solution")
        assert len(matches) == 1

    @pytest.mark.parametrize("term,text", [
        ("C++", "I love C++ programming"),
        ("C++", "C++ is great"),        # term at the very start of the text
        ("C++", "I code in C++"),       # term at the very end of the text
    ])
    def test_term_ending_in_punctuation_is_matched_correctly(self, term, text):
        glossary = Glossary(terms=[GlossaryTerm(term=term, translatable=False, context="", translations={})])
        matches = glossary.find_matches(text)
        assert len(matches) == 1
        assert matches[0].matched_text == term