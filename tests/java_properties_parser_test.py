import logging

import pytest

from babelfishers.core.parsers.java_properties_parser import JavaPropertiesParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_properties(tmp_path):
    def _write(content: str, filename: str = "source.properties"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return JavaPropertiesParser()


def _unit_by_key(units, key):
    return next(u for u in units if u.key == key)


class TestJavaPropertiesParserParse:
    def test_raises_value_error_when_file_extension_is_not_properties(self, parser, tmp_path):
        invalid_file = tmp_path / "source.txt"
        invalid_file.write_text("app.title=My App", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_simple_key_value_pairs(self, parser, write_properties):
        source = write_properties("app.title=My App\napp.version=1.0\n")
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"app.title", "app.version"}
        assert _unit_by_key(result.units, "app.title").source_text == "My App"

    def test_ignores_hash_comment_lines(self, parser, write_properties):
        source = write_properties("# a comment\napp.title=My App\n")
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["app.title"]

    def test_ignores_bang_comment_lines(self, parser, write_properties):
        source = write_properties("! a comment\napp.title=My App\n")
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["app.title"]

    def test_ignores_blank_lines(self, parser, write_properties):
        source = write_properties("app.title=My App\n\napp.version=1.0\n")
        result = parser.parse(source, [])

        assert {u.key for u in result.units} == {"app.title", "app.version"}

    def test_supports_colon_as_separator(self, parser, write_properties):
        source = write_properties("app.title: My App\n")
        result = parser.parse(source, [])

        assert result.units[0].key == "app.title"
        assert result.units[0].source_text == "My App"

    def test_supports_whitespace_as_separator(self, parser, write_properties):
        source = write_properties("app.title My App\n")
        result = parser.parse(source, [])

        assert result.units[0].key == "app.title"
        assert result.units[0].source_text == "My App"

    def test_decodes_unicode_escapes_in_value(self, parser, write_properties):
        source = write_properties("greeting=Caf\\u00e9\n")
        result = parser.parse(source, [])

        assert result.units[0].source_text == "Café"

    def test_line_continuation_joins_next_line(self, parser, write_properties):
        source = write_properties("greeting=Hello \\\nWorld\n")
        result = parser.parse(source, [])

        assert result.units[0].source_text == "Hello World"

    def test_excludes_key_in_excluded_keys(self, parser, write_properties):
        source = write_properties("app.title=My App\napp.internal=Debug\n")
        result = parser.parse(source, ["app.internal"])

        assert [u.key for u in result.units] == ["app.title"]

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_or_whitespace_only_value_produces_no_unit(self, parser, write_properties, value):
        source = write_properties(f"app.title=My App\nblank={value}\n")
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["app.title"]

    def test_duplicate_key_logs_a_warning(self, parser, write_properties, caplog):
        source = write_properties("dup=first\ndup=second\n")

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate properties key" in r.message for r in caplog.records)
        assert result.units[-1].source_text == "second"

    def test_preserves_crlf_line_endings_on_save(self, parser, write_properties, tmp_path):
        source = write_properties("app.title=My App\r\napp.version=1.0\r\n")
        result = parser.parse(source, [])

        destination = tmp_path / "out.properties"
        result.save(destination)

        assert destination.read_bytes() == b"app.title=My App\r\napp.version=1.0\r\n"

    def test_preserves_lf_line_endings_on_save(self, parser, write_properties, tmp_path):
        source = write_properties("app.title=My App\napp.version=1.0\n")
        result = parser.parse(source, [])

        destination = tmp_path / "out.properties"
        result.save(destination)

        assert destination.read_bytes() == b"app.title=My App\napp.version=1.0\n"

    def test_all_units_are_tagged_with_properties_resource_type(self, parser, write_properties):
        source = write_properties("app.title=My App\n")
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.JAVA_PROPERTIES for u in result.units)

    def test_write_back_mutates_the_document_entry(self, parser, write_properties, tmp_path):
        source = write_properties("app.title=My App\n")
        result = parser.parse(source, [])

        result.units[0].write_back("Mon Application")

        destination = tmp_path / "out.properties"
        result.save(destination)

        assert "app.title=Mon Application" in destination.read_text(encoding="utf-8")

    def test_save_preserves_comments(self, parser, write_properties, tmp_path):
        source = write_properties("# a comment\napp.title=My App\n")
        result = parser.parse(source, [])

        destination = tmp_path / "out.properties"
        result.save(destination)

        content = destination.read_text(encoding="utf-8")
        assert "# a comment" in content
        assert "app.title=My App" in content

    def test_save_creates_parent_directories_if_missing(self, parser, write_properties, tmp_path):
        source = write_properties("app.title=My App\n")
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.properties"
        result.save(destination)

        assert "app.title=My App" in destination.read_text(encoding="utf-8")


class TestJavaPropertiesParserClone:
    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_properties):
        source = write_properties("app.title=My App\n")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Mon Application")

        assert cloned.document[0]["value"] == "Mon Application"
        assert original.document[0]["value"] == "My App"

    def test_clone_handles_duplicate_keys_by_occurrence_order(self, parser, write_properties):
        source = write_properties("dup=first\ndup=second\n")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("changed-first")

        assert cloned.document[0]["value"] == "changed-first"
        assert cloned.document[1]["value"] == "second"

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_properties, tmp_path):
        source = write_properties("app.title=My App\n")
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Mon Application")

        destination = tmp_path / "out.properties"
        cloned.save(destination)

        assert "app.title=Mon Application" in destination.read_text(encoding="utf-8")
