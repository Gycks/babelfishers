import logging

import pytest

from babelfishers.core.parsers.apple_strings_parser import AppleStringsParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_strings(tmp_path):
    def _write(content: str, filename: str = "Localizable.strings"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return AppleStringsParser()


def _unit_by_key(units, key):
    return next(u for u in units if u.key == key)


class TestAppleStringsParserParse:
    def test_raises_value_error_when_file_extension_is_not_strings(self, parser, tmp_path):
        invalid_file = tmp_path / "source.txt"
        invalid_file.write_text('"greeting" = "Hello";', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_key_value_entries(self, parser, write_strings):
        source = write_strings('"greeting" = "Hello";\n"farewell" = "Bye";\n')
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"greeting", "farewell"}
        assert _unit_by_key(result.units, "greeting").source_text == "Hello"

    def test_block_comment_becomes_context_hint(self, parser, write_strings):
        source = write_strings('/* Shown on the home screen */\n"greeting" = "Hello";\n')
        result = parser.parse(source, [])

        assert result.units[0].context_hint == "Shown on the home screen"

    def test_entries_without_comment_have_no_context_hint(self, parser, write_strings):
        source = write_strings('"greeting" = "Hello";\n')
        result = parser.parse(source, [])

        assert result.units[0].context_hint is None

    def test_excludes_key_in_excluded_keys(self, parser, write_strings):
        source = write_strings('"greeting" = "Hello";\n"internal" = "Debug";\n')
        result = parser.parse(source, ["internal"])

        assert [u.key for u in result.units] == ["greeting"]

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_or_whitespace_only_value_produces_no_unit(self, parser, write_strings, value):
        source = write_strings(f'"greeting" = "Hello";\n"blank" = "{value}";\n')
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["greeting"]

    def test_duplicate_key_logs_a_warning(self, parser, write_strings, caplog):
        source = write_strings('"dup" = "first";\n"dup" = "second";\n')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate .strings key" in r.message for r in caplog.records)
        assert result.units[-1].source_text == "second"

    def test_unrecognized_content_is_preserved_and_logs_a_warning(self, parser, write_strings, tmp_path, caplog):
        source = write_strings('"greeting" = "Hello";\nnot a real entry\n"farewell" = "Bye";\n')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Preserving unrecognized" in r.message for r in caplog.records)
        assert {u.key for u in result.units} == {"greeting", "farewell"}

        destination = tmp_path / "out.strings"
        result.save(destination)
        assert "not a real entry" in destination.read_text(encoding="utf-8")

    def test_preserves_crlf_line_endings_on_save(self, parser, write_strings, tmp_path):
        source = write_strings('"greeting" = "Hello";\r\n"farewell" = "Bye";\r\n')
        result = parser.parse(source, [])

        destination = tmp_path / "out.strings"
        result.save(destination)

        assert destination.read_bytes() == b'"greeting" = "Hello";\r\n"farewell" = "Bye";\r\n'

    def test_all_units_are_tagged_with_apple_strings_resource_type(self, parser, write_strings):
        source = write_strings('"greeting" = "Hello";\n')
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.APPLE_STRINGS for u in result.units)

    def test_write_back_mutates_the_value(self, parser, write_strings, tmp_path):
        source = write_strings('"greeting" = "Hello";\n')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.strings"
        result.save(destination)

        assert '"greeting" = "Bonjour";' in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_strings, tmp_path):
        source = write_strings('"greeting" = "Hello";\n')
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.strings"
        result.save(destination)

        assert '"greeting" = "Hello";' in destination.read_text(encoding="utf-8")


class TestAppleStringsParserClone:
    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_strings):
        source = write_strings('"greeting" = "Hello";\n')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        assert cloned.document[0]["value"] == "Bonjour"
        assert original.document[0]["value"] == "Hello"

    def test_clone_handles_duplicate_keys_by_occurrence_order(self, parser, write_strings):
        source = write_strings('"dup" = "first";\n"dup" = "second";\n')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("changed-first")

        assert cloned.document[0]["value"] == "changed-first"
        assert cloned.document[1]["value"] == "second"

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_strings, tmp_path):
        source = write_strings('"greeting" = "Hello";\n')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        destination = tmp_path / "out.strings"
        cloned.save(destination)

        assert '"greeting" = "Bonjour";' in destination.read_text(encoding="utf-8")
