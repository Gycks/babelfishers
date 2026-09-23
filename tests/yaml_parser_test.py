import logging

import pytest
import yaml

from babelfishers.core.parsers.yaml_parser import YAMLParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_yaml(tmp_path):
    def _write(content: dict, filename: str = "source.yaml"):
        path = tmp_path / filename
        path.write_text(yaml.safe_dump(content), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_raw_yaml(tmp_path):
    def _write(content: str, filename: str = "source.yaml"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return YAMLParser()


def _unit_by_key(units, key):
    return next(u for u in units if u.key == key)


class TestYAMLParserParse:
    def test_raises_value_error_when_file_extension_is_not_yaml(self, parser, tmp_path):
        invalid_file = tmp_path / "source.json"
        invalid_file.write_text('{"en": {"greeting": "Hello"}}', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_accepts_yml_extension(self, parser, write_yaml):
        source = write_yaml({"en": {"greeting": "Hello"}}, filename="source.yml")
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["en.greeting"]

    def test_parses_flat_string_values_into_translation_units(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello", "farewell": "Bye"})
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"greeting", "farewell"}
        assert _unit_by_key(result.units, "greeting").source_text == "Hello"

    def test_parses_nested_dict_using_dotted_key_path(self, parser, write_yaml):
        source = write_yaml({"en": {"section": {"title": "Welcome"}}})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["en.section.title"]
        assert result.units[0].source_text == "Welcome"

    def test_parses_list_items_using_bracket_index_in_key(self, parser, write_yaml):
        source = write_yaml({"items": ["first", "second"]})
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"items[0]", "items[1]"}

    def test_parses_list_of_dicts_using_combined_bracket_and_dot_key(self, parser, write_yaml):
        source = write_yaml({"items": [{"name": "Widget"}]})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["items[0].name"]
        assert result.units[0].source_text == "Widget"

    def test_excludes_top_level_key_in_excluded_keys(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello", "internal": "Debug"})
        result = parser.parse(source, ["internal"])

        assert [u.key for u in result.units] == ["greeting"]

    def test_excludes_nested_key_in_excluded_keys(self, parser, write_yaml):
        source = write_yaml({"section": {"title": "Welcome", "secret": "Hidden"}})
        result = parser.parse(source, ["section.secret"])

        assert [u.key for u in result.units] == ["section.title"]

    def test_empty_dict_produces_no_units(self, parser, write_yaml):
        source = write_yaml({})
        result = parser.parse(source, [])

        assert result.units == []

    def test_non_string_leaf_values_are_silently_dropped(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello", "count": 42, "enabled": True})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["greeting"]

    @pytest.mark.parametrize("value", ["", "   ", "\n\t"])
    def test_empty_or_whitespace_only_string_values_produce_no_unit(self, parser, write_yaml, value):
        source = write_yaml({"greeting": "Hello", "blank": value})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["greeting"]

    def test_duplicate_key_logs_a_warning(self, parser, write_raw_yaml, caplog):
        source = write_raw_yaml("greeting: Hello\ngreeting: Bonjour\n")

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate YAML key" in r.message for r in caplog.records)
        assert result.units[0].source_text == "Bonjour"

    def test_document_field_holds_the_parsed_raw_structure(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello"})
        result = parser.parse(source, [])

        assert result.document == {"greeting": "Hello"}

    def test_all_units_are_tagged_with_yaml_resource_type(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello"})
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.YAML for u in result.units)

    def test_write_back_mutates_the_correct_dict_key(self, parser, write_yaml):
        source = write_yaml({"section": {"title": "Welcome"}})
        result = parser.parse(source, [])

        _unit_by_key(result.units, "section.title").write_back("Bienvenue")

        assert result.document["section"]["title"] == "Bienvenue"

    def test_save_preserves_unicode_characters(self, parser, write_yaml, tmp_path):
        source = write_yaml({"greeting": "Café"})
        result = parser.parse(source, [])

        destination = tmp_path / "out.yaml"
        result.save(destination)

        assert "Café" in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_yaml, tmp_path):
        source = write_yaml({"greeting": "Hello"})
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.yaml"
        result.save(destination)

        assert yaml.safe_load(destination.read_text(encoding="utf-8")) == {"greeting": "Hello"}


class TestYAMLParserClone:
    def test_clone_document_is_a_deep_copy_independent_from_original(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.document["greeting"] = "changed"

        assert original.document["greeting"] == "Hello"

    def test_clone_units_preserve_key_source_text_and_unit_type(self, parser, write_yaml):
        source = write_yaml({"section": {"title": "Welcome"}})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]
        assert [u.unit_type for u in cloned.units] == [u.unit_type for u in original.units]

    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_yaml):
        source = write_yaml({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "greeting").write_back("Bonjour")

        assert cloned.document["greeting"] == "Bonjour"
        assert original.document["greeting"] == "Hello"

    def test_clone_write_back_resolves_list_index_path_correctly(self, parser, write_yaml):
        source = write_yaml({"items": ["x", "y"]})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "items[1]").write_back("translated")

        assert cloned.document["items"] == ["x", "translated"]

    def test_clone_of_empty_units_list_returns_empty_units_list(self, parser, write_yaml):
        source = write_yaml({})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert cloned.units == []

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_yaml, tmp_path):
        source = write_yaml({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "greeting").write_back("Bonjour")

        destination = tmp_path / "out.yaml"
        cloned.save(destination)

        assert yaml.safe_load(destination.read_text(encoding="utf-8")) == {"greeting": "Bonjour"}
