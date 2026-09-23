import logging

import pytest

from babelfishers.core.guards.toolkit import find_placeholders
from babelfishers.core.parsers.xliff_parser import XLIFFParser
from babelfishers.models.translation_resource import TranslationResourceType


_XLIFF_TEMPLATE = (
    '<xliff version="1.2"><file source-language="en" target-language="fr">'
    "<body>{body}</body></file></xliff>"
)


@pytest.fixture
def write_xliff(tmp_path):
    def _write(body: str, filename: str = "source.xliff"):
        path = tmp_path / filename
        path.write_text(_XLIFF_TEMPLATE.format(body=body), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return XLIFFParser()


class TestXLIFFParserParse:
    def test_raises_value_error_when_file_extension_is_not_xliff_or_xlf(self, parser, tmp_path):
        invalid_file = tmp_path / "source.xml"
        invalid_file.write_text("<xliff></xliff>", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_accepts_xlf_extension(self, parser, write_xliff):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>', filename="source.xlf")
        result = parser.parse(source, [])

        assert result.units[0].key == "greeting"

    def test_parses_trans_unit_source_into_translation_unit(self, parser, write_xliff):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        result = parser.parse(source, [])

        assert result.units[0].key == "greeting"
        assert result.units[0].source_text == "Hello"

    def test_note_element_becomes_context_hint(self, parser, write_xliff):
        source = write_xliff(
            '<trans-unit id="greeting"><source>Hello</source><note>Shown on homepage</note></trans-unit>'
        )
        result = parser.parse(source, [])

        assert result.units[0].context_hint == "Shown on homepage"

    def test_excludes_key_in_excluded_keys(self, parser, write_xliff):
        source = write_xliff(
            '<trans-unit id="greeting"><source>Hello</source></trans-unit>'
            '<trans-unit id="internal"><source>Debug</source></trans-unit>'
        )
        result = parser.parse(source, ["internal"])

        assert [u.key for u in result.units] == ["greeting"]

    def test_all_units_are_tagged_with_xliff_resource_type(self, parser, write_xliff):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.XLIFF for u in result.units)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_or_whitespace_only_source_produces_no_unit(self, parser, write_xliff, value):
        source = write_xliff(f'<trans-unit id="blank"><source>{value}</source></trans-unit>')
        result = parser.parse(source, [])

        assert result.units == []

    def test_trans_unit_with_no_id_logs_a_warning_and_is_skipped(self, parser, write_xliff, caplog):
        source = write_xliff("<trans-unit><source>Hello</source></trans-unit>")

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("no 'id' attribute" in r.message for r in caplog.records)
        assert result.units == []

    def test_trans_unit_with_no_source_logs_a_warning_and_is_skipped(self, parser, write_xliff, caplog):
        source = write_xliff('<trans-unit id="greeting"></trans-unit>')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("no <source>" in r.message for r in caplog.records)
        assert result.units == []

    def test_duplicate_trans_unit_id_logs_a_warning(self, parser, write_xliff, caplog):
        source = write_xliff(
            '<trans-unit id="dup"><source>first</source></trans-unit>'
            '<trans-unit id="dup"><source>second</source></trans-unit>'
        )

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate unit id" in r.message for r in caplog.records)
        assert result.units[0].source_text == "second"

    def test_preserves_xml_comments_on_save(self, parser, write_xliff, tmp_path):
        source = write_xliff('<!-- section note --><trans-unit id="greeting"><source>Hello</source></trans-unit>')
        result = parser.parse(source, [])

        destination = tmp_path / "out.xliff"
        result.save(destination)

        assert "<!-- section note -->" in destination.read_text(encoding="utf-8")

    def test_writes_a_double_quoted_xml_declaration(self, parser, write_xliff, tmp_path):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        result = parser.parse(source, [])

        destination = tmp_path / "out.xliff"
        result.save(destination)

        first_line = destination.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == '<?xml version="1.0" encoding="utf-8"?>'

    def test_inline_markup_is_not_truncated(self, parser, write_xliff):
        source = write_xliff('<trans-unit id="greeting"><source>Hello <g id="1">world</g>!</source></trans-unit>')
        result = parser.parse(source, [])

        assert result.units[0].source_text == 'Hello <g id="1">world</g>!'

    def test_write_back_with_inline_markup_round_trips_the_tag(self, parser, write_xliff, tmp_path):
        source = write_xliff('<trans-unit id="greeting"><source>Hello <g id="1">world</g>!</source></trans-unit>')
        result = parser.parse(source, [])

        spans = find_placeholders(result.units[0].source_text, result.units[0].unit_type)
        result.units[0].write_back(f"Bonjour {spans[0].matched_text} !")

        destination = tmp_path / "out.xliff"
        result.save(destination)
        content = destination.read_text(encoding="utf-8")

        assert '<source>Hello <g id="1">world</g>!</source>' in content
        assert '<target>Bonjour <g id="1">world</g> !</target>' in content

    def test_write_back_populates_missing_target_without_touching_source(self, parser, write_xliff, tmp_path):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.xliff"
        result.save(destination)

        content = destination.read_text(encoding="utf-8")
        assert "<source>Hello</source>" in content
        assert "<target>Bonjour</target>" in content

    def test_write_back_overwrites_existing_target(self, parser, write_xliff, tmp_path):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source><target></target></trans-unit>')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.xliff"
        result.save(destination)

        assert "<target>Bonjour</target>" in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_xliff, tmp_path):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.xliff"
        result.save(destination)

        assert "Hello" in destination.read_text(encoding="utf-8")


class TestXLIFFParserClone:
    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_xliff):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        cloned_target = cloned.document.find(".//trans-unit/target")
        original_target = original.document.find(".//trans-unit/target")
        assert cloned_target.text == "Bonjour"
        assert original_target.text is None

    def test_clone_units_preserve_key_and_source_text(self, parser, write_xliff):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_xliff, tmp_path):
        source = write_xliff('<trans-unit id="greeting"><source>Hello</source></trans-unit>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        destination = tmp_path / "out.xliff"
        cloned.save(destination)

        assert "<target>Bonjour</target>" in destination.read_text(encoding="utf-8")
