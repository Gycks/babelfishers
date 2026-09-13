import logging

import pytest

from babelfishers.core.parsers.gettext_parser import GettextParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_po(tmp_path):
    def _write(content: str, filename: str = "source.po"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return GettextParser()


class TestGettextParserParse:
    def test_raises_value_error_when_file_extension_is_not_po(self, parser, tmp_path):
        invalid_file = tmp_path / "source.txt"
        invalid_file.write_text('msgid "Hello"\nmsgstr ""\n', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_simple_entry_into_translation_unit(self, parser, write_po):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        result = parser.parse(source, [])

        assert result.units[0].key == "Hello"
        assert result.units[0].source_text == "Hello"

    def test_skips_the_empty_header_entry(self, parser, write_po):
        source = write_po('msgid ""\nmsgstr "Content-Type: text/plain\\n"\n\nmsgid "Hello"\nmsgstr ""\n')
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["Hello"]

    def test_extracted_comment_becomes_context_hint(self, parser, write_po):
        source = write_po('#. Shown on the home screen\nmsgid "Hello"\nmsgstr ""\n')
        result = parser.parse(source, [])

        assert result.units[0].context_hint == "Shown on the home screen"

    def test_msgctxt_disambiguates_identical_msgids(self, parser, write_po):
        source = write_po(
            'msgctxt "menu"\nmsgid "Open"\nmsgstr ""\n\nmsgctxt "file"\nmsgid "Open"\nmsgstr ""\n'
        )
        result = parser.parse(source, [])

        assert len(result.units) == 2
        assert result.units[0].key != result.units[1].key

    def test_plural_forms_produce_indexed_units(self, parser, write_po):
        source = write_po(
            'msgid "one item"\nmsgid_plural "%d items"\nmsgstr[0] ""\nmsgstr[1] ""\n'
        )
        result = parser.parse(source, [])

        keys = [u.key for u in result.units]
        assert keys == ["one item[0]", "one item[1]"]
        assert result.units[0].source_text == "one item"
        assert result.units[1].source_text == "%d items"

    def test_excludes_entry_matching_excluded_keys(self, parser, write_po):
        source = write_po('msgid "Hello"\nmsgstr ""\n\nmsgid "Internal"\nmsgstr ""\n')
        result = parser.parse(source, ["Internal"])

        assert [u.key for u in result.units] == ["Hello"]

    def test_duplicate_msgid_logs_a_warning(self, parser, write_po, caplog):
        source = write_po('msgid "Hello"\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n')

        with caplog.at_level(logging.WARNING):
            parser.parse(source, [])

        assert any("Duplicate PO msgid" in r.message for r in caplog.records)

    def test_unrecognized_syntax_logs_a_warning_and_is_dropped(self, parser, write_po, caplog):
        source = write_po('msgid "Hello"\nnot valid po syntax\nmsgstr ""\n')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Ignoring unrecognized PO syntax" in r.message for r in caplog.records)
        assert result.units[0].source_text == "Hello"

    def test_preserves_crlf_line_endings_on_save(self, parser, write_po, tmp_path):
        source = write_po('msgid "Hello"\r\nmsgstr ""\r\n')
        result = parser.parse(source, [])

        destination = tmp_path / "out.po"
        result.save(destination)

        assert destination.read_bytes() == b'msgid "Hello"\r\nmsgstr ""\r\n'

    def test_all_units_are_tagged_with_gettext_resource_type(self, parser, write_po):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.GETTEXT for u in result.units)

    def test_write_back_mutates_singular_msgstr(self, parser, write_po, tmp_path):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.po"
        result.save(destination)

        assert 'msgstr "Bonjour"' in destination.read_text(encoding="utf-8")

    def test_write_back_mutates_plural_msgstr_index(self, parser, write_po, tmp_path):
        source = write_po('msgid "one item"\nmsgid_plural "%d items"\nmsgstr[0] ""\nmsgstr[1] ""\n')
        result = parser.parse(source, [])

        result.units[1].write_back("%d articles")

        destination = tmp_path / "out.po"
        result.save(destination)

        assert 'msgstr[1] "%d articles"' in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_po, tmp_path):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.po"
        result.save(destination)

        assert 'msgid "Hello"' in destination.read_text(encoding="utf-8")


class TestGettextParserClone:
    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_po):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        assert cloned.document[0]["msgstr"] == "Bonjour"
        assert original.document[0]["msgstr"] == ""

    def test_clone_units_preserve_key_and_source_text(self, parser, write_po):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_po, tmp_path):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        destination = tmp_path / "out.po"
        cloned.save(destination)

        assert 'msgstr "Bonjour"' in destination.read_text(encoding="utf-8")
