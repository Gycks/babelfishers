import logging

import pytest

from babelfishers.core.guards.toolkit import find_placeholders
from babelfishers.core.parsers.android_strings_parser import AndroidStringsParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_xml(tmp_path):
    def _write(content: str, filename: str = "strings.xml"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return AndroidStringsParser()


def _unit_by_key(units, key):
    return next(u for u in units if u.key == key)


class TestAndroidStringsParserParse:
    def test_raises_value_error_when_file_extension_is_not_xml(self, parser, tmp_path):
        invalid_file = tmp_path / "strings.json"
        invalid_file.write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_string_elements_into_translation_units(self, parser, write_xml):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        result = parser.parse(source, [])

        assert result.units[0].key == "title"
        assert result.units[0].source_text == "Hello"

    def test_excludes_string_marked_not_translatable(self, parser, write_xml):
        source = write_xml(
            '<resources><string name="title">Hello</string>'
            '<string name="debug" translatable="false">DEBUG</string></resources>'
        )
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["title"]

    def test_parses_string_array_items_using_bracket_index(self, parser, write_xml):
        source = write_xml(
            '<resources><string-array name="colors"><item>Red</item><item>Blue</item></string-array></resources>'
        )
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"colors[0]", "colors[1]"}
        assert _unit_by_key(result.units, "colors[0]").source_text == "Red"

    def test_excludes_string_array_marked_not_translatable(self, parser, write_xml):
        source = write_xml(
            '<resources><string-array name="colors" translatable="false"><item>Red</item></string-array></resources>'
        )
        result = parser.parse(source, [])

        assert result.units == []

    def test_parses_plurals_items_using_dotted_quantity_key(self, parser, write_xml):
        source = write_xml(
            '<resources><plurals name="num_messages">'
            '<item quantity="one">%d message</item>'
            '<item quantity="other">%d messages</item>'
            "</plurals></resources>"
        )
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"num_messages.one", "num_messages.other"}
        assert _unit_by_key(result.units, "num_messages.one").source_text == "%d message"

    def test_excludes_plurals_marked_not_translatable(self, parser, write_xml):
        source = write_xml(
            '<resources><plurals name="num_messages" translatable="false">'
            '<item quantity="one">%d message</item>'
            "</plurals></resources>"
        )
        result = parser.parse(source, [])

        assert result.units == []

    def test_excludes_key_in_excluded_keys(self, parser, write_xml):
        source = write_xml(
            '<resources><string name="title">Hello</string><string name="internal">Debug</string></resources>'
        )
        result = parser.parse(source, ["internal"])

        assert [u.key for u in result.units] == ["title"]

    def test_all_units_are_tagged_with_android_resource_type(self, parser, write_xml):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.ANDROID_STRINGS for u in result.units)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_or_whitespace_only_string_produces_no_unit(self, parser, write_xml, value):
        source = write_xml(f'<resources><string name="title">Hello</string><string name="blank">{value}</string></resources>')
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["title"]

    def test_string_with_no_name_attribute_logs_a_warning_and_is_skipped(self, parser, write_xml, caplog):
        source = write_xml('<resources><string>Hello</string></resources>')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("no 'name' attribute" in r.message for r in caplog.records)
        assert result.units == []

    def test_plural_item_with_no_quantity_logs_a_warning_and_is_skipped(self, parser, write_xml, caplog):
        source = write_xml('<resources><plurals name="n"><item>%d thing</item></plurals></resources>')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("no 'quantity'" in r.message for r in caplog.records)
        assert result.units == []

    def test_duplicate_string_name_logs_a_warning(self, parser, write_xml, caplog):
        source = write_xml('<resources><string name="dup">first</string><string name="dup">second</string></resources>')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate Android string key" in r.message for r in caplog.records)
        assert result.units[0].source_text == "second"

    def test_preserves_xml_comments_on_save(self, parser, write_xml, tmp_path):
        source = write_xml('<resources><!-- section note --><string name="title">Hello</string></resources>')
        result = parser.parse(source, [])

        destination = tmp_path / "out.xml"
        result.save(destination)

        assert "<!-- section note -->" in destination.read_text(encoding="utf-8")

    def test_writes_a_double_quoted_xml_declaration(self, parser, write_xml, tmp_path):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        result = parser.parse(source, [])

        destination = tmp_path / "out.xml"
        result.save(destination)

        first_line = destination.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == '<?xml version="1.0" encoding="utf-8"?>'

    def test_inline_markup_is_not_truncated(self, parser, write_xml):
        source = write_xml(
            '<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">'
            '<string name="count">Sent <xliff:g id="count">%d</xliff:g> messages</string>'
            "</resources>"
        )
        result = parser.parse(source, [])

        assert result.units[0].source_text.startswith("Sent <xliff:g")
        assert result.units[0].source_text.endswith("</xliff:g> messages")
        assert "%d" in result.units[0].source_text

    def test_write_back_with_inline_markup_round_trips_the_tag(self, parser, write_xml, tmp_path):
        source = write_xml(
            '<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">'
            '<string name="count">Sent <xliff:g id="count">%d</xliff:g> messages</string>'
            "</resources>"
        )
        result = parser.parse(source, [])

        spans = find_placeholders(result.units[0].source_text, result.units[0].unit_type)
        result.units[0].write_back(f"Envoye {spans[0].matched_text} messages")

        destination = tmp_path / "out.xml"
        result.save(destination)
        content = destination.read_text(encoding="utf-8")

        assert '<xliff:g id="count">%d</xliff:g>' in content
        assert "Envoye" in content

    def test_write_back_mutates_the_element_text(self, parser, write_xml, tmp_path):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.xml"
        result.save(destination)

        assert "Bonjour" in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_xml, tmp_path):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.xml"
        result.save(destination)

        assert "Hello" in destination.read_text(encoding="utf-8")


class TestAndroidStringsParserClone:
    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_xml):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        assert cloned.document.find("string").text == "Bonjour"
        assert original.document.find("string").text == "Hello"

    def test_clone_units_preserve_key_and_source_text(self, parser, write_xml):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_xml, tmp_path):
        source = write_xml('<resources><string name="title">Hello</string></resources>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        destination = tmp_path / "out.xml"
        cloned.save(destination)

        assert "Bonjour" in destination.read_text(encoding="utf-8")
