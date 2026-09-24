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

    def test_clone_for_target_locale_rewrites_language_and_plural_forms_in_the_header(self, parser, write_po):
        source = write_po(
            'msgid ""\nmsgstr ""\n"Project-Id-Version: demo\\n"\n"Language: en\\n"\n'
            '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\nmsgid "Hello"\nmsgstr ""\n'
        )
        cloned = parser.clone(parser.parse(source, []), "pl")

        assert cloned.document[0]["msgstr"] == (
            "Project-Id-Version: demo\n"
            "Language: pl\n"
            "Plural-Forms: nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);\n"
        )

    def test_clone_for_target_locale_adds_a_header_when_the_source_has_none(self, parser, write_po):
        source = write_po('msgid "Hello"\nmsgstr ""\n')
        cloned = parser.clone(parser.parse(source, []), "fr")

        assert cloned.document[0]["msgid"] == ""
        assert cloned.document[0]["msgstr"] == (
            "Content-Type: text/plain; charset=UTF-8\nLanguage: fr\nPlural-Forms: nplurals=2; plural=(n > 1);\n"
        )
        assert [u.key for u in cloned.units] == ["Hello"]

    @pytest.mark.parametrize(
        ("locale", "expected_sources"),
        [
            ("fr", ["one item", "%d items"]),
            ("pl", ["one item", "%d items", "%d items"]),
            ("ar", ["%d items", "one item", "%d items", "%d items", "%d items", "%d items"]),
            ("ja", ["%d items"]),
        ],
    )
    def test_clone_for_target_locale_emits_one_plural_unit_per_target_form(
        self, parser, write_po, locale, expected_sources
    ):
        source = write_po('msgid "one item"\nmsgid_plural "%d items"\nmsgstr[0] ""\nmsgstr[1] ""\n')
        cloned = parser.clone(parser.parse(source, []), locale)

        assert [u.key for u in cloned.units] == [f"one item[{i}]" for i in range(len(expected_sources))]
        assert [u.source_text for u in cloned.units] == expected_sources

    def test_clone_for_target_locale_saves_every_target_plural_slot(self, parser, write_po, tmp_path):
        source = write_po('msgid "one item"\nmsgid_plural "%d items"\nmsgstr[0] ""\nmsgstr[1] ""\n')
        cloned = parser.clone(parser.parse(source, []), "ru")

        for unit in cloned.units:
            unit.write_back(f"form {unit.key[-2]}")

        destination = tmp_path / "out.po"
        cloned.save(destination)

        text = destination.read_text(encoding="utf-8")
        assert 'msgstr[0] "form 0"\nmsgstr[1] "form 1"\nmsgstr[2] "form 2"\n' in text
        assert "msgstr[3]" not in text

    def test_clone_for_target_locale_keeps_excluded_plural_slots_out_of_the_units(self, parser, write_po):
        source = write_po('msgid "one item"\nmsgid_plural "%d items"\nmsgstr[0] ""\nmsgstr[1] "kept"\n')
        cloned = parser.clone(parser.parse(source, ["one item[1]"]), "pl")

        assert [u.key for u in cloned.units] == ["one item[0]", "one item[2]"]
        assert cloned.document[1]["msgstr_plural"] == {0: "", 1: "kept", 2: ""}

    def test_clone_for_unknown_locale_sets_language_and_keeps_source_plural_forms(self, parser, write_po, caplog):
        source = write_po(
            'msgid ""\nmsgstr ""\n"Language: en\\n"\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'
            'msgid "one item"\nmsgid_plural "%d items"\nmsgstr[0] ""\nmsgstr[1] ""\n'
        )

        with caplog.at_level(logging.WARNING):
            cloned = parser.clone(parser.parse(source, []), "xx")

        assert any("No gettext plural rule known for 'xx'" in r.message for r in caplog.records)
        assert cloned.document[0]["msgstr"] == "Language: xx\nPlural-Forms: nplurals=2; plural=(n != 1);\n"
        assert [u.key for u in cloned.units] == ["one item[0]", "one item[1]"]
