import json

import pytest

from babelfishers.core.parsers.json_parser import JSONParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_json(tmp_path):
    def _write(content, filename: str = "source.json"):
        path = tmp_path / filename
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return JSONParser()


def _unit_by_key(units, key):
    return next(u for u in units if u.key == key)


class TestJSONParserParse:
    def test_parses_flat_string_values_into_translation_units(self, parser, write_json):
        source = write_json({"greeting": "Hello", "farewell": "Bye"})
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"greeting", "farewell"}
        assert _unit_by_key(result.units, "greeting").source_text == "Hello"

    def test_parses_nested_dict_using_dotted_key_path(self, parser, write_json):
        source = write_json({"section": {"title": "Welcome"}})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["section.title"]
        assert result.units[0].source_text == "Welcome"

    def test_parses_list_items_using_bracket_index_in_key(self, parser, write_json):
        source = write_json({"items": ["first", "second"]})
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"items[0]", "items[1]"}

    def test_parses_list_of_dicts_using_combined_bracket_and_dot_key(self, parser, write_json):
        source = write_json({"items": [{"name": "Widget"}]})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["items[0].name"]
        assert result.units[0].source_text == "Widget"

    def test_multi_digit_list_index_is_parsed_correctly(self, parser, write_json):
        source = write_json({"items": [f"value-{i}" for i in range(11)]})
        result = parser.parse(source, [])

        last = _unit_by_key(result.units, "items[10]")
        assert last.source_text == "value-10"

    def test_excludes_top_level_key_in_excluded_keys(self, parser, write_json):
        source = write_json({"greeting": "Hello", "internal": "Debug"})
        result = parser.parse(source, ["internal"])

        assert [u.key for u in result.units] == ["greeting"]

    def test_excludes_nested_key_in_excluded_keys(self, parser, write_json):
        source = write_json({"section": {"title": "Welcome", "secret": "Hidden"}})
        result = parser.parse(source, ["section.secret"])

        assert [u.key for u in result.units] == ["section.title"]

    def test_excludes_list_item_index_key_in_excluded_keys(self, parser, write_json):
        source = write_json({"items": ["first", "second"]})
        result = parser.parse(source, ["items[1]"])

        assert [u.key for u in result.units] == ["items[0]"]

    def test_empty_list_produces_no_units(self, parser, write_json):
        source = write_json({"items": []})
        result = parser.parse(source, [])

        assert result.units == []

    @pytest.mark.parametrize("value", [42, 3.14, True, False, None])
    def test_non_string_leaf_values_are_silently_dropped(self, parser, write_json, value):
        source = write_json({"greeting": "Hello", "leaf": value})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["greeting"]

    def test_empty_dict_produces_no_units(self, parser, write_json):
        source = write_json({})
        result = parser.parse(source, [])

        assert result.units == []

    def test_document_field_holds_the_parsed_raw_dict(self, parser, write_json):
        source = write_json({"greeting": "Hello"})
        result = parser.parse(source, [])

        assert result.document == {"greeting": "Hello"}

    def test_all_units_are_tagged_with_json_resource_type(self, parser, write_json):
        source = write_json({"greeting": "Hello"})
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.JSON for u in result.units)

    def test_write_back_mutates_the_correct_dict_key(self, parser, write_json):
        source = write_json({"section": {"title": "Welcome"}})
        result = parser.parse(source, [])

        _unit_by_key(result.units, "section.title").write_back("Bienvenue")

        assert result.document["section"]["title"] == "Bienvenue"

    def test_write_back_mutates_the_correct_list_index(self, parser, write_json):
        source = write_json({"items": ["first", "second"]})
        result = parser.parse(source, [])

        _unit_by_key(result.units, "items[1]").write_back("deuxieme")

        assert result.document["items"] == ["first", "deuxieme"]

    def test_save_preserves_unicode_characters(self, parser, write_json, tmp_path):
        source = write_json({"greeting": "Café"})
        result = parser.parse(source, [])

        destination = tmp_path / "out.json"
        result.save(destination)

        assert "Café" in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_json, tmp_path):
        source = write_json({"greeting": "Hello"})
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.json"
        result.save(destination)

        assert json.loads(destination.read_text(encoding="utf-8")) == {"greeting": "Hello"}

    def test_raises_value_error_when_file_extension_is_not_json(self, parser, tmp_path):
        invalid_file = tmp_path / "source.html"
        invalid_file.write_text("<html><body>Hello</body></html>", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])


class TestJSONParserClone:
    def test_clone_document_is_a_deep_copy_independent_from_original(self, parser, write_json):
        source = write_json({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.document["greeting"] = "changed"

        assert original.document["greeting"] == "Hello"

    def test_clone_units_preserve_key_source_text_and_unit_type(self, parser, write_json):
        source = write_json({"section": {"title": "Welcome"}})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]
        assert [u.unit_type for u in cloned.units] == [u.unit_type for u in original.units]

    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_json):
        source = write_json({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "greeting").write_back("Bonjour")

        assert cloned.document["greeting"] == "Bonjour"
        assert original.document["greeting"] == "Hello"

    def test_clone_original_write_back_still_targets_original_document(self, parser, write_json):
        source = write_json({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(original.units, "greeting").write_back("Bonjour")

        assert original.document["greeting"] == "Bonjour"
        assert cloned.document["greeting"] == "Hello"

    def test_clone_write_back_resolves_nested_dict_path_correctly(self, parser, write_json):
        source = write_json({"a": {"b": "text"}})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "a.b").write_back("translated")

        assert cloned.document["a"]["b"] == "translated"

    def test_clone_write_back_resolves_list_index_path_correctly(self, parser, write_json):
        source = write_json({"items": ["x", "y"]})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "items[1]").write_back("translated")

        assert cloned.document["items"] == ["x", "translated"]

    def test_clone_write_back_resolves_combined_list_and_dict_path_correctly(self, parser, write_json):
        source = write_json({"items": [{"name": "x"}]})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "items[0].name").write_back("translated")

        assert cloned.document["items"][0]["name"] == "translated"

    def test_clone_of_empty_units_list_returns_empty_units_list(self, parser, write_json):
        source = write_json({})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert cloned.units == []

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_json, tmp_path):
        source = write_json({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "greeting").write_back("Bonjour")

        destination = tmp_path / "out.json"
        cloned.save(destination)

        assert json.loads(destination.read_text(encoding="utf-8")) == {"greeting": "Bonjour"}
