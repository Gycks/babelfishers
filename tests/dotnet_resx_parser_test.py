import logging

import pytest

from babelfishers.core.parsers.dotnet_resx_parser import DotNetResxParser
from babelfishers.models.translation_resource import TranslationResourceType


_RESX_TEMPLATE = "<root>{body}</root>"


@pytest.fixture
def write_resx(tmp_path):
    def _write(body: str, filename: str = "source.resx"):
        path = tmp_path / filename
        path.write_text(_RESX_TEMPLATE.format(body=body), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return DotNetResxParser()


class TestDotNetResxParserParse:
    def test_raises_value_error_when_file_extension_is_not_resx(self, parser, tmp_path):
        invalid_file = tmp_path / "source.xml"
        invalid_file.write_text("<root></root>", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_parses_data_value_into_translation_unit(self, parser, write_resx):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        result = parser.parse(source, [])

        assert result.units[0].key == "Greeting"
        assert result.units[0].source_text == "Hello"

    def test_comment_element_becomes_context_hint(self, parser, write_resx):
        source = write_resx('<data name="Greeting"><value>Hello</value><comment>Shown on homepage</comment></data>')
        result = parser.parse(source, [])

        assert result.units[0].context_hint == "Shown on homepage"

    def test_excludes_data_element_with_type_attribute(self, parser, write_resx):
        source = write_resx(
            '<data name="Greeting"><value>Hello</value></data>'
            '<data name="Icon" type="System.Drawing.Bitmap, System.Drawing"><value>base64data</value></data>'
        )
        result = parser.parse(source, [])

        assert [u.key for u in result.units] == ["Greeting"]

    def test_excludes_key_in_excluded_keys(self, parser, write_resx):
        source = write_resx(
            '<data name="Greeting"><value>Hello</value></data>'
            '<data name="Internal"><value>Debug</value></data>'
        )
        result = parser.parse(source, ["Internal"])

        assert [u.key for u in result.units] == ["Greeting"]

    def test_all_units_are_tagged_with_dotnet_resx_resource_type(self, parser, write_resx):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        result = parser.parse(source, [])

        assert all(u.unit_type == TranslationResourceType.DOTNET_RESX for u in result.units)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_or_whitespace_only_value_produces_no_unit(self, parser, write_resx, value):
        source = write_resx(f'<data name="Blank"><value>{value}</value></data>')
        result = parser.parse(source, [])

        assert result.units == []

    def test_data_with_no_name_logs_a_warning_and_is_skipped(self, parser, write_resx, caplog):
        source = write_resx("<data><value>Hello</value></data>")

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("no 'name' attribute" in r.message for r in caplog.records)
        assert result.units == []

    def test_data_with_no_value_logs_a_warning_and_is_skipped(self, parser, write_resx, caplog):
        source = write_resx('<data name="Greeting"></data>')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("no <value>" in r.message for r in caplog.records)
        assert result.units == []

    def test_duplicate_data_name_logs_a_warning(self, parser, write_resx, caplog):
        source = write_resx('<data name="dup"><value>first</value></data><data name="dup"><value>second</value></data>')

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source, [])

        assert any("Duplicate resx data name" in r.message for r in caplog.records)
        assert result.units[0].source_text == "second"

    def test_preserves_xml_comments_on_save(self, parser, write_resx, tmp_path):
        source = write_resx('<!-- section note --><data name="Greeting"><value>Hello</value></data>')
        result = parser.parse(source, [])

        destination = tmp_path / "out.resx"
        result.save(destination)

        assert "<!-- section note -->" in destination.read_text(encoding="utf-8")

    def test_writes_a_double_quoted_xml_declaration(self, parser, write_resx, tmp_path):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        result = parser.parse(source, [])

        destination = tmp_path / "out.resx"
        result.save(destination)

        first_line = destination.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == '<?xml version="1.0" encoding="utf-8"?>'

    def test_cdata_value_stays_cdata_after_translation(self, parser, write_resx, tmp_path):
        source = write_resx('<data name="Greeting"><value><![CDATA[Hello <b>world</b>]]></value></data>')
        result = parser.parse(source, [])

        assert result.units[0].source_text == "Hello <b>world</b>"

        result.units[0].write_back("Bonjour <b>monde</b>")
        destination = tmp_path / "out.resx"
        result.save(destination)

        assert "<![CDATA[Bonjour <b>monde</b>]]>" in destination.read_text(encoding="utf-8")

    def test_plain_value_stays_plain_after_translation(self, parser, write_resx, tmp_path):
        source = write_resx('<data name="Greeting"><value>Hello &amp; welcome</value></data>')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour & bienvenue")
        destination = tmp_path / "out.resx"
        result.save(destination)

        content = destination.read_text(encoding="utf-8")
        assert "<![CDATA[" not in content
        assert "Bonjour &amp; bienvenue" in content

    def test_write_back_mutates_the_value_element(self, parser, write_resx, tmp_path):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        result = parser.parse(source, [])

        result.units[0].write_back("Bonjour")

        destination = tmp_path / "out.resx"
        result.save(destination)

        assert "<value>Bonjour</value>" in destination.read_text(encoding="utf-8")

    def test_save_creates_parent_directories_if_missing(self, parser, write_resx, tmp_path):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        result = parser.parse(source, [])

        destination = tmp_path / "nested" / "dir" / "out.resx"
        result.save(destination)

        assert "Hello" in destination.read_text(encoding="utf-8")


class TestDotNetResxParserClone:
    def test_clone_write_back_writes_to_cloned_document_only(self, parser, write_resx):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        cloned_value = cloned.document.find(".//data/value")
        original_value = original.document.find(".//data/value")
        assert cloned_value.text == "Bonjour"
        assert original_value.text == "Hello"

    def test_clone_units_preserve_key_and_source_text(self, parser, write_resx):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        assert [u.key for u in cloned.units] == [u.key for u in original.units]
        assert [u.source_text for u in cloned.units] == [u.source_text for u in original.units]

    def test_clone_save_writes_the_cloned_document_not_the_original(self, parser, write_resx, tmp_path):
        source = write_resx('<data name="Greeting"><value>Hello</value></data>')
        original = parser.parse(source, [])
        cloned = parser.clone(original)

        cloned.units[0].write_back("Bonjour")

        destination = tmp_path / "out.resx"
        cloned.save(destination)

        assert "<value>Bonjour</value>" in destination.read_text(encoding="utf-8")
