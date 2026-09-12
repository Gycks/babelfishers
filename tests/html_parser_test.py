import logging

import pytest
from bs4 import BeautifulSoup

from babelfishers.core.parsers.html_parser import HTMLParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_html(tmp_path):
    def _write(content: str, filename: str = "source.html"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return HTMLParser()


def _texts(units):
    return [u.source_text for u in units]


class TestHTMLParserParse:
    def test_raises_value_error_when_file_extension_is_not_html(self, parser, tmp_path):
        invalid_file = tmp_path / "source.json"
        invalid_file.write_text('{"greeting": "Hello"}', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_visible_text_nodes_into_translation_units(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p><p>World</p></body></html>")
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello", "World"]

    def test_excludes_script_and_style_content(self, parser, write_html):
        source = write_html(
            "<html><body><p>Hello</p><script>var x = 1;</script>"
            "<style>p { color: red; }</style></body></html>"
        )
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello"]

    def test_excludes_head_title_meta_link_noscript_content(self, parser, write_html):
        source = write_html(
            "<html><head><title>Ignored</title><meta name=\"x\" content=\"y\">"
            "<link rel=\"stylesheet\" href=\"a.css\"><noscript>No JS</noscript></head>"
            "<body><p>Hello</p></body></html>"
        )
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello"]

    def test_excludes_html_comments(self, parser, write_html):
        source = write_html("<html><body><!-- a comment --><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello"]

    def test_excludes_doctype(self, parser, write_html):
        source = write_html("<!DOCTYPE html><html><body><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello"]

    def test_whitespace_only_text_nodes_produce_no_units(self, parser, write_html):
        source = write_html("<html><body>\n   \n<p>Hello</p>\n   \n</body></html>")
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello"]

    def test_translate_no_attribute_excludes_subtree(self, parser, write_html):
        source = write_html(
            "<html><body><p>Hello</p><p translate=\"no\">Skip me</p></body></html>"
        )
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Hello"]

    def test_translate_yes_overrides_ancestor_translate_no(self, parser, write_html):
        source = write_html(
            "<html><body><div translate=\"no\">Skip <span translate=\"yes\">Keep</span></div></body></html>"
        )
        result = parser.parse(source, [])

        assert _texts(result.units) == ["Keep"]

    def test_excludes_elements_matching_excluded_keys_selector(self, parser, write_html):
        source = write_html(
            "<html><body><p>Hello</p><div class=\"legal\">Do not translate</div></body></html>"
        )
        result = parser.parse(source, [".legal"])

        assert _texts(result.units) == ["Hello"]

    def test_invalid_excluded_keys_selector_is_ignored_with_warning(self, parser, write_html, caplog):
        source = write_html("<html><body><p>Hello</p></body></html>")

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, ["[[["])

        assert _texts(result.units) == ["Hello"]
        assert any("Ignoring invalid excluded_keys selector" in r.message for r in caplog.records)

    def test_all_units_are_tagged_with_html_resource_type(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.HTML for u in result.units)

    def test_each_unit_key_is_unique(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        keys = [u.key for u in result.units]
        assert len(keys) == len(set(keys))

    def test_write_back_mutates_the_source_document(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        assert "Bonjour" in str(result.document)
        assert "Hello" not in str(result.document)

    def test_document_field_holds_the_parsed_soup(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        assert isinstance(result.document, BeautifulSoup)

    def test_save_preserves_unicode_characters(self, parser, write_html, tmp_path):
        source = write_html("<html><body><p>Café</p></body></html>")
        result = parser.parse(source, [])

        destination = tmp_path / "out.html"
        result.save(destination)

        assert "Café" in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_html, tmp_path):
        source = write_html("<html><body><p>Hello</p></body></html>")
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.html"
        result.save(destination)

        assert "Hello" in destination.read_text(encoding="utf-8")


class TestHTMLParserClone:
    def test_clone_document_is_independent_from_original(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p></body></html>")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert cloned.document is not original.document

    def test_clone_units_preserve_key_source_text_and_unit_type(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p><p>World</p></body></html>")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]
        assert [u.unit_type for u in cloned.units] == [u.unit_type for u in original.units]

    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p></body></html>")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        assert "Bonjour" in str(cloned.document)
        assert "Bonjour" not in str(original.document)

    def test_clone_original_write_back_still_targets_original_document(self, parser, write_html):
        source = write_html("<html><body><p>Hello</p></body></html>")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        original.units[0].write_back("Bonjour")

        assert "Bonjour" in str(original.document)
        assert "Bonjour" not in str(cloned.document)

    def test_clone_of_empty_units_list_returns_empty_units_list(self, parser, write_html):
        source = write_html("<html><body></body></html>")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert cloned.units == []

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_html, tmp_path):
        source = write_html("<html><body><p>Hello</p></body></html>")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        destination = tmp_path / "out.html"
        cloned.save(destination)

        assert "Bonjour" in destination.read_text(encoding="utf-8")
