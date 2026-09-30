import logging

import pytest

from babelfishers.core.csv_layout import CsvOptions, detect_csv_layout
from babelfishers.core.parsers.csv_parser import CSVParser
from babelfishers.models.translation_resource import TranslationResourceType


@pytest.fixture
def write_csv(tmp_path):
    def _write(text, filename="strings.csv", encoding="utf-8"):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode(encoding))
        return path

    return _write


@pytest.fixture
def parser():
    return CSVParser("en")


def _translate(parser, source, locale, destination, transform=None):
    transform = transform or (lambda text: f"[{locale}] {text}")
    cloned = parser.clone(parser.parse(source, []), locale)
    for unit in cloned.units:
        unit.write_back(transform(unit.source_text))
    cloned.save(destination)
    return destination.read_text(encoding="utf-8")


def _remember(parser, source, locale):
    cloned = parser.clone(parser.parse(source, []), locale)
    for unit in cloned.units:
        unit.write_back(f"[{locale}] {unit.source_text}")
    cloned.save(source)
    recorded = dict(cloned.translated_from)
    parser.use_translated_from(lambda path, target_locale: recorded if target_locale == locale else {})
    return recorded


class TestCsvLayoutDetection:
    def test_a_column_for_the_source_locale_makes_the_file_wide(self, write_csv):
        layout = detect_csv_layout(write_csv("key,en,fr,comment\n"), "en")

        assert layout.wide
        assert (layout.key, layout.source, layout.context, layout.locales) == (0, 1, 3, {"en": 1, "fr": 2})

    def test_a_value_column_without_locale_columns_makes_the_file_narrow(self, write_csv):
        layout = detect_csv_layout(write_csv("key,value,description\n"), "en")

        assert not layout.wide
        assert (layout.key, layout.source, layout.context) == (0, 1, 2)

    def test_role_names_are_read_before_locale_codes(self, write_csv):
        layout = detect_csv_layout(write_csv("id,value\n"), "en")

        assert not layout.wide
        assert layout.key == 0

    def test_headers_are_compared_ignoring_case_and_spaces(self, write_csv):
        layout = detect_csv_layout(write_csv(" Key , EN ,Fr\n"), "en")

        assert layout.locales == {"en": 1, "fr": 2}

    def test_the_tag_in_parentheses_names_the_locale(self, write_csv):
        layout = detect_csv_layout(write_csv("Keys,English(en),French(fr)\n"), "en")

        assert layout.locales == {"en": 1, "fr": 2}

    def test_the_first_column_is_the_key_when_none_is_named(self, write_csv):
        layout = detect_csv_layout(write_csv("label,en,de\n"), "en")

        assert layout.key == 0

    def test_unknown_columns_are_ignored(self, write_csv):
        layout = detect_csv_layout(write_csv("key,en,max_length,fr\n"), "en")

        assert layout.locales == {"en": 1, "fr": 3}

    @pytest.mark.parametrize(
        ("text", "delimiter"),
        [("key;en;fr\n", ";"), ("key\ten\tfr\n", "\t"), ("key|en|fr\n", "|"), ("key,en,fr\n", ",")],
    )
    def test_the_delimiter_is_the_most_frequent_one_in_the_header(self, write_csv, text, delimiter):
        assert detect_csv_layout(write_csv(text), "en").delimiter == delimiter

    def test_a_tsv_file_is_tab_separated(self, write_csv):
        layout = detect_csv_layout(write_csv("key\ten\tnote,a,b,c\n", filename="strings.tsv"), "en")

        assert (layout.delimiter, layout.locales) == ("\t", {"en": 1})

    def test_the_delimiter_option_wins(self, write_csv):
        layout = detect_csv_layout(write_csv("key;en;notes,a,b\n"), "en", CsvOptions(delimiter=";"))

        assert (layout.delimiter, layout.locales) == (";", {"en": 1})

    def test_the_columns_option_maps_roles_and_locales(self, write_csv):
        options = CsvOptions.from_mapping({"columns": {"key": "String ID", "en": "English", "fr": "Français"}})

        layout = detect_csv_layout(write_csv("String ID,English,Français,Notes\n"), "en", options)

        assert (layout.key, layout.locales, layout.context) == (0, {"en": 1, "fr": 2}, 3)

    def test_a_locale_column_that_is_not_supported_fails(self, write_csv):
        with pytest.raises(ValueError, match="'pt-ao', which is not supported"):
            detect_csv_layout(write_csv("key,en,pt-AO\n"), "en")

    def test_locale_columns_without_the_source_locale_fail(self, write_csv):
        with pytest.raises(ValueError, match="none for the source locale 'en'"):
            detect_csv_layout(write_csv("key,fr,de\n"), "en")

    def test_a_source_locale_and_a_value_column_together_fail(self, write_csv):
        with pytest.raises(ValueError, match="ambiguous"):
            detect_csv_layout(write_csv("key,en,value\n"), "en")

    def test_a_header_without_a_known_column_fails(self, write_csv):
        with pytest.raises(ValueError, match="Can't tell the layout"):
            detect_csv_layout(write_csv("Hello,Bonjour\n"), "en")

    def test_an_empty_file_fails(self, write_csv):
        with pytest.raises(ValueError, match="no header row"):
            detect_csv_layout(write_csv(""), "en")

    def test_a_locale_in_the_first_column_without_a_key_column_fails(self, write_csv):
        with pytest.raises(ValueError, match="no key column"):
            detect_csv_layout(write_csv("en,fr\n"), "en")

    def test_two_columns_with_the_same_role_fail(self, write_csv):
        with pytest.raises(ValueError, match="more than one key column"):
            detect_csv_layout(write_csv("key,id,value\n"), "en")

    @pytest.mark.parametrize(
        ("header", "locale"),
        [("key,en,fr,French(fr)", "fr"), ("key,en,pt,pt-PT", "pt-pt")],
    )
    def test_two_columns_for_the_same_locale_fail(self, write_csv, header, locale):
        with pytest.raises(ValueError, match=f"more than one column for the locale '{locale}'"):
            detect_csv_layout(write_csv(f"{header}\n"), "en")

    @pytest.mark.parametrize(("header", "source"), [("key,en-US,fr", "en"), ("key,en,fr", "en-US")])
    def test_the_source_column_may_use_the_plain_code_or_the_variant(self, write_csv, header, source):
        layout = detect_csv_layout(write_csv(f"{header}\n"), source)

        assert (layout.wide, layout.source) == (True, 1)

    def test_a_file_that_is_not_utf8_fails(self, write_csv):
        with pytest.raises(ValueError, match="UTF-8"):
            detect_csv_layout(write_csv("key,en\ncafé,Café\n", encoding="latin-1"), "en")


class TestCsvOptions:
    def test_an_unknown_option_fails(self):
        with pytest.raises(ValueError, match="Unknown csv option"):
            CsvOptions.from_mapping({"sheet": "Main"})

    def test_an_unsupported_delimiter_fails(self):
        with pytest.raises(ValueError, match="Invalid csv delimiter"):
            CsvOptions.from_mapping({"delimiter": ":"})

    def test_a_columns_entry_that_is_not_a_role_or_a_supported_locale_fails(self):
        with pytest.raises(ValueError, match="'xx' is neither"):
            CsvOptions.from_mapping({"columns": {"xx": "Klingon"}})

    def test_a_columns_entry_for_a_column_the_file_lacks_fails(self, write_csv):
        options = CsvOptions.from_mapping({"columns": {"en": "English"}})

        with pytest.raises(ValueError, match="no column 'English'"):
            detect_csv_layout(write_csv("key,en\n"), "en", options)


class TestCsvParserParse:
    def test_raises_value_error_when_file_extension_is_not_csv(self, parser, write_csv):
        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(write_csv("key,en\n", filename="strings.txt"), [])

    def test_the_source_column_of_a_wide_file_is_the_source_text(self, parser, write_csv):
        source = write_csv("key,en,fr,comment\ngreeting,Hello,,Home title\n")

        units = parser.parse(source, []).units

        assert [(u.key, u.source_text, u.context_hint) for u in units] == [("greeting", "Hello", "Home title")]

    def test_the_value_column_of_a_narrow_file_is_the_source_text(self, parser, write_csv):
        source = write_csv("key,value\ngreeting,Hello\n", filename="en/strings.csv")

        assert [(u.key, u.source_text) for u in parser.parse(source, []).units] == [("greeting", "Hello")]

    def test_empty_values_blank_rows_and_excluded_keys_are_skipped(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\nempty,\n\nbrand,Babel Fishers\n")

        assert [u.key for u in parser.parse(source, ["brand"]).units] == ["greeting"]

    def test_a_row_without_a_key_is_skipped_with_a_warning(self, parser, write_csv, caplog):
        source = write_csv("key,en\n,Orphan\ngreeting,Hello\n")

        with caplog.at_level(logging.WARNING):
            units = parser.parse(source, []).units

        assert [u.key for u in units] == ["greeting"]
        assert any("row 2" in r.message for r in caplog.records)

    def test_a_cell_with_a_newline_is_one_value(self, parser, write_csv):
        source = write_csv('key,en\naddress,"Line 1\nLine 2"\n')

        assert parser.parse(source, []).units[0].source_text == "Line 1\nLine 2"

    def test_all_units_are_tagged_with_csv_resource_type(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\n")

        assert all(u.unit_type == TranslationResourceType.CSV for u in parser.parse(source, []).units)

    def test_raises_without_a_configured_source_locale(self):
        with pytest.raises(ValueError, match="source locale"):
            CSVParser()


class TestCsvParserWide:
    def test_fills_the_target_column_and_keeps_everything_else(self, parser, write_csv):
        source = write_csv("key,en,fr,comment\ngreeting,Hello,,Home\nbye,Bye,Au revoir,\n")

        text = _translate(parser, source, "fr", source)

        assert text == "key,en,fr,comment\ngreeting,Hello,[fr] Hello,Home\nbye,Bye,Au revoir,\n"

    def test_a_plain_target_code_fills_the_column_of_its_variant(self, parser, write_csv):
        source = write_csv("key,en,pt-PT\ngreeting,Hello,\n")

        assert _translate(parser, source, "pt", source) == "key,en,pt-PT\ngreeting,Hello,[pt] Hello\n"

    def test_a_target_locale_without_a_column_gets_one_appended(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\n")

        assert _translate(parser, source, "de", source) == "key,en,de\ngreeting,Hello,[de] Hello\n"

    def test_short_rows_are_padded_to_reach_the_target_column(self, parser, write_csv):
        source = write_csv("key,en,comment,fr\ngreeting,Hello\n")

        assert _translate(parser, source, "fr", source) == "key,en,comment,fr\ngreeting,Hello,,[fr] Hello\n"

    def test_saving_one_locale_keeps_what_another_locale_wrote_meanwhile(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\n")
        parsed = parser.parse(source, [])
        fr, de = parser.clone(parsed, "fr"), parser.clone(parsed, "de")
        fr.units[0].write_back("Bonjour")
        de.units[0].write_back("Hallo")

        fr.save(source)
        de.save(source)

        assert source.read_text(encoding="utf-8") == "key,en,fr,de\ngreeting,Hello,Bonjour,Hallo\n"

    def test_the_delimiter_line_endings_bom_and_quoting_are_kept(self, parser, write_csv):
        source = write_csv('\ufeffkey;en;fr\r\ngreeting;"Hello; world";\r\n')

        _translate(parser, source, "fr", source)

        assert source.read_bytes().decode("utf-8") == '\ufeffkey;en;fr\r\ngreeting;"Hello; world";"[fr] Hello; world"\r\n'

    def test_a_file_without_a_final_newline_stays_without_one(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello")

        assert _translate(parser, source, "fr", source) == "key,en,fr\ngreeting,Hello,[fr] Hello"

    @pytest.mark.parametrize("target", ["EN", "en-US"])
    def test_a_target_that_is_the_source_locale_is_skipped_with_a_warning(self, parser, write_csv, caplog, target):
        source = write_csv("key,en\ngreeting,Hello\n")

        with caplog.at_level(logging.WARNING):
            assert parser.clone(parser.parse(source, []), target).units == []

        assert any("source locale" in r.message for r in caplog.records)

    def test_a_filled_cell_without_a_record_is_kept(self, parser, write_csv):
        source = write_csv("key,en,fr\ngreeting,Hi,Bonjour\n")

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_cell_is_left_alone_while_its_source_is_the_same(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\n")
        _remember(parser, source, "fr")

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_cell_is_translated_again_when_its_source_changed(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\nbye,Bye\n")
        _remember(parser, source, "fr")
        source.write_text(source.read_text(encoding="utf-8").replace(",Hello,", ",Hi,"), encoding="utf-8")

        units = parser.clone(parser.parse(source, []), "fr").units

        assert [(u.key, u.source_text) for u in units] == [("greeting", "Hi")]

    def test_the_record_keeps_rows_left_alone_and_drops_keys_no_longer_in_the_file(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\n")
        recorded = _remember(parser, source, "fr")
        parser.use_translated_from(lambda path, locale: {**recorded, "gone": "0123456789abcdef"})

        assert parser.clone(parser.parse(source, []), "fr").translated_from == recorded

    def test_has_target_is_false_until_every_row_has_its_translation(self, parser, write_csv):
        source = write_csv("key,en\ngreeting,Hello\n")
        assert not parser.has_target(source, source, "fr", [])

        _remember(parser, source, "fr")

        assert parser.has_target(source, source, "fr", [])

    def test_content_hash_ignores_target_columns_and_changes_with_the_source(self, parser, write_csv):
        source = write_csv("key,en,comment\ngreeting,Hello,Home\n")
        before = parser.content_hash(source)

        _translate(parser, source, "fr", source)
        assert parser.content_hash(source) == before

        write_csv("key,en,comment,fr\ngreeting,Hello,Settings,[fr] Hello\n")
        assert parser.content_hash(source) != before

    def test_saving_a_file_that_was_not_cloned_for_a_locale_raises(self, parser, write_csv, tmp_path):
        source = write_csv("key,en\ngreeting,Hello\n")

        with pytest.raises(ValueError, match="clone it"):
            parser.parse(source, []).save(tmp_path / "out.csv")


class TestCsvParserNarrow:
    def test_writes_a_copy_with_the_translated_values(self, parser, write_csv, tmp_path):
        source = write_csv("key,value,comment\ngreeting,Hello,Home\n", filename="en/strings.csv")
        destination = tmp_path / "fr/strings.csv"

        text = _translate(parser, source, "fr", destination)

        assert text == "key,value,comment\ngreeting,[fr] Hello,Home\n"
        assert source.read_text(encoding="utf-8") == "key,value,comment\ngreeting,Hello,Home\n"

    def test_every_row_is_translated_again_on_each_run(self, parser, write_csv, tmp_path):
        source = write_csv("key,value\ngreeting,Hello\n", filename="en/strings.csv")
        _translate(parser, source, "fr", tmp_path / "fr/strings.csv")

        assert [u.key for u in parser.clone(parser.parse(source, []), "fr").units] == ["greeting"]

    def test_has_target_is_whether_the_destination_exists(self, parser, write_csv, tmp_path):
        source = write_csv("key,value\ngreeting,Hello\n", filename="en/strings.csv")
        destination = tmp_path / "fr/strings.csv"
        assert not parser.has_target(source, destination, "fr", [])

        _translate(parser, source, "fr", destination)

        assert parser.has_target(source, destination, "fr", [])
