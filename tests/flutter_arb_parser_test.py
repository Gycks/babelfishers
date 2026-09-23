import json
import logging

import pytest

from babelfishers.core.parsers.flutter_arb_parser import FlutterArbParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_arb(tmp_path):
    def _write(content, filename: str = "app_en.arb"):
        path = tmp_path / filename
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_raw_arb(tmp_path):
    def _write(content: str, filename: str = "app_en.arb"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return FlutterArbParser()


def _unit_by_key(units, key):
    return next(u for u in units if u.key == key)


class TestFlutterArbParserParse:
    def test_raises_value_error_when_file_extension_is_not_arb(self, parser, tmp_path):
        invalid_file = tmp_path / "source.json"
        invalid_file.write_text('{"greeting": "Hello"}', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_flat_string_values_into_translation_units(self, parser, write_arb):
        source = write_arb({"greeting": "Hello", "farewell": "Bye"})
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"greeting", "farewell"}
        assert _unit_by_key(result.units, "greeting").source_text == "Hello"

    def test_skips_at_prefixed_metadata_keys(self, parser, write_arb):
        source = write_arb(
            {
                "@@locale": "en",
                "greeting": "Hello {name}",
                "@greeting": {"description": "Greeting shown to the user"},
            }
        )
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["greeting"]

    def test_parses_nested_dict_using_dotted_key_path(self, parser, write_arb):
        source = write_arb({"section": {"title": "Welcome"}})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["section.title"]

    def test_parses_list_items_using_bracket_index_in_key(self, parser, write_arb):
        source = write_arb({"items": ["first", "second"]})
        result = parser.parse(source, [])

        keys = {u.key for u in result.units}
        assert keys == {"items[0]", "items[1]"}

    def test_excludes_key_in_excluded_keys(self, parser, write_arb):
        source = write_arb({"greeting": "Hello", "internal": "Debug"})
        result = parser.parse(source, ["internal"])

        assert [u.key for u in result.units] == ["greeting"]

    @pytest.mark.parametrize("value", ["", "   ", "\n\t"])
    def test_empty_or_whitespace_only_string_values_produce_no_unit(self, parser, write_arb, value):
        source = write_arb({"greeting": "Hello", "blank": value})
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["greeting"]

    def test_duplicate_key_logs_a_warning(self, parser, write_raw_arb, caplog):
        source = write_raw_arb('{"greeting": "Hello", "greeting": "Bonjour"}')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate ARB key" in r.message for r in caplog.records)
        assert result.units[0].source_text == "Bonjour"

    def test_all_units_are_tagged_with_flutter_arb_resource_type(self, parser, write_arb):
        source = write_arb({"greeting": "Hello"})
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.FLUTTER_ARB for u in result.units)

    def test_write_back_mutates_the_correct_dict_key(self, parser, write_arb):
        source = write_arb({"greeting": "Hello"})
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        assert result.document["greeting"] == "Bonjour"

    def test_save_preserves_metadata_untouched(self, parser, write_arb, tmp_path):
        source = write_arb({"greeting": "Hello", "@greeting": {"description": "hi"}})
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.arb"
        result.save(destination)

        saved = json.loads(destination.read_text(encoding="utf-8"))
        assert saved["greeting"] == "Bonjour"
        assert saved["@greeting"] == {"description": "hi"}

    def test_save_creates_parent_directories_if_missing(self, parser, write_arb, tmp_path):
        source = write_arb({"greeting": "Hello"})
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.arb"
        result.save(destination)

        assert json.loads(destination.read_text(encoding="utf-8")) == {"greeting": "Hello"}


class TestFlutterArbParserClone:
    def test_clone_document_is_a_deep_copy_independent_from_original(self, parser, write_arb):
        source = write_arb({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.document["greeting"] = "changed"

        assert original.document["greeting"] == "Hello"

    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_arb):
        source = write_arb({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "greeting").write_back("Bonjour")

        assert cloned.document["greeting"] == "Bonjour"
        assert original.document["greeting"] == "Hello"

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_arb, tmp_path):
        source = write_arb({"greeting": "Hello"})
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        _unit_by_key(cloned.units, "greeting").write_back("Bonjour")

        destination = tmp_path / "out.arb"
        cloned.save(destination)

        assert json.loads(destination.read_text(encoding="utf-8")) == {"greeting": "Bonjour"}
