import json
import logging

import pytest

from babelfishers.core.parsers.xcstrings_parser import XCStringParser
from babelfishers.models.translation_resource import TranslationResourceType


def _su(value, state="translated"):
    return {"stringUnit": {"state": state, "value": value}}


def _mt(value):
    return _su(value, state="needs_review")


def _catalog(strings, source="en"):
    return {"sourceLanguage": source, "strings": strings, "version": "1.0"}


@pytest.fixture
def write_catalog(tmp_path):
    def _write(catalog, filename="Localizable.xcstrings"):
        path = tmp_path / filename
        path.write_text(json.dumps(catalog), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def parser():
    return XCStringParser("en")


def _translate(parser, source, locale, destination, transform=None):
    transform = transform or (lambda text: f"[{locale}] {text}")
    cloned = parser.clone(parser.parse(source, []), locale)
    for unit in cloned.units:
        unit.write_back(transform(unit.source_text))
    cloned.save(destination)
    return json.loads(destination.read_text(encoding="utf-8"))


def _remember(parser, source, locale):
    cloned = parser.clone(parser.parse(source, []), locale)
    for unit in cloned.units:
        unit.write_back(f"[{locale}] {unit.source_text}")
    cloned.save(source)
    recorded = dict(cloned.translated_from)
    parser.use_translated_from(lambda path, target_locale: recorded if target_locale == locale else {})
    return recorded


def _set_source(source, key, value):
    catalog = json.loads(source.read_text(encoding="utf-8"))
    catalog["strings"][key]["localizations"]["en"] = _su(value)
    source.write_text(json.dumps(catalog), encoding="utf-8")


def _approve(source, key, locale):
    catalog = json.loads(source.read_text(encoding="utf-8"))
    catalog["strings"][key]["localizations"][locale]["stringUnit"]["state"] = "translated"
    source.write_text(json.dumps(catalog), encoding="utf-8")


class TestXcstringsParserParse:
    def test_raises_value_error_when_file_extension_is_not_xcstrings(self, parser, tmp_path):
        invalid_file = tmp_path / "source.json"
        invalid_file.write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid file extension"):
            parser.parse(invalid_file, [])

    def test_returns_none_and_logs_an_error_when_source_language_is_missing(self, parser, tmp_path, caplog):
        source = tmp_path / "Localizable.xcstrings"
        source.write_text('{"strings": {}}', encoding="utf-8")

        with caplog.at_level(logging.ERROR):
            assert parser.parse(source, []) is None

        assert any("sourceLanguage" in r.message for r in caplog.records)

    def test_returns_none_and_logs_an_error_when_source_language_is_not_the_configured_one(self, write_catalog, caplog):
        source = write_catalog(_catalog({"greeting": {}}, source="de"))

        with caplog.at_level(logging.ERROR):
            assert XCStringParser("en").parse(source, []) is None

        assert any("'de'" in r.message and "'en'" in r.message for r in caplog.records)

    @pytest.mark.parametrize("source_language", [1, "", None])
    def test_returns_none_and_logs_an_error_when_source_language_is_not_text(
        self, parser, write_catalog, caplog, source_language
    ):
        source = write_catalog({"sourceLanguage": source_language, "strings": {"greeting": {}}})

        with caplog.at_level(logging.ERROR):
            assert parser.parse(source, []) is None

        assert any("sourceLanguage" in r.message for r in caplog.records)

    def test_raises_value_error_without_a_configured_source_locale(self):
        with pytest.raises(ValueError, match="source locale"):
            XCStringParser()

    def test_null_strings_is_an_empty_catalog(self, parser, write_catalog):
        source = write_catalog({"sourceLanguage": "en", "strings": None})

        assert parser.parse(source, []).units == []

    def test_source_language_is_compared_ignoring_case(self, write_catalog):
        source = write_catalog(_catalog({"greeting": {}}, source="EN"))

        assert [u.key for u in XCStringParser("en").parse(source, []).units] == ["greeting"]

    def test_source_localization_value_is_the_source_text(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))

        assert [(u.key, u.source_text) for u in parser.parse(source, []).units] == [("greeting", "Hello")]

    def test_key_is_the_source_text_when_there_is_no_source_localization(self, parser, write_catalog):
        source = write_catalog(_catalog({"Hello, world": {}}))

        assert parser.parse(source, []).units[0].source_text == "Hello, world"

    def test_comment_becomes_context_hint(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"comment": "Home screen title"}}))

        assert parser.parse(source, []).units[0].context_hint == "Home screen title"

    def test_excludes_key_in_excluded_keys(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {}, "internal": {}}))

        assert [u.key for u in parser.parse(source, ["internal"]).units] == ["greeting"]

    def test_skips_strings_marked_should_translate_false_and_stale_ones(self, parser, write_catalog):
        source = write_catalog(
            _catalog(
                {
                    "greeting": {},
                    "brand": {"shouldTranslate": False},
                    "removed": {"extractionState": "stale"},
                }
            )
        )

        assert [u.key for u in parser.parse(source, []).units] == ["greeting"]

    def test_all_units_are_tagged_with_xcstrings_resource_type(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {}}))

        assert all(u.unit_type == TranslationResourceType.XCSTRINGS for u in parser.parse(source, []).units)


class TestXcstringsParserTranslate:
    def test_writes_the_target_into_the_same_catalog_and_keeps_the_source(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))

        result = _translate(parser, source, "fr", source)

        assert result["strings"]["greeting"]["localizations"] == {"en": _su("Hello"), "fr": _mt("[fr] Hello")}

    def test_fills_only_targets_that_are_not_translated_yet(self, parser, write_catalog):
        source = write_catalog(
            _catalog(
                {
                    "kept": {"localizations": {"fr": _su("Approuvé")}},
                    "review": {"localizations": {"fr": _su("Ancien", state="needs_review")}},
                    "new": {},
                }
            )
        )

        result = _translate(parser, source, "fr", source)

        fr = {key: entry["localizations"]["fr"] for key, entry in result["strings"].items()}
        assert fr == {"kept": _su("Approuvé"), "review": _mt("[fr] review"), "new": _mt("[fr] new")}

    def test_a_string_without_source_localization_is_translated_from_its_key(self, parser, write_catalog):
        source = write_catalog(_catalog({"Hello, world": {}}))

        result = _translate(parser, source, "fr", source)

        assert result["strings"]["Hello, world"]["localizations"]["fr"] == _mt("[fr] Hello, world")

    def test_plural_group_gets_the_categories_the_target_needs(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural}}}))

        result = _translate(parser, source, "ru", source)

        categories = result["strings"]["files"]["localizations"]["ru"]["variations"]["plural"]
        assert categories == {
            "one": _mt("[ru] %d file"),
            "few": _mt("[ru] %d files"),
            "many": _mt("[ru] %d files"),
            "other": _mt("[ru] %d files"),
        }

    def test_plural_group_of_a_language_with_one_form_keeps_only_other(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural}}}))

        result = _translate(parser, source, "ja", source)

        categories = result["strings"]["files"]["localizations"]["ja"]["variations"]["plural"]
        assert categories == {"other": _mt("[ja] %d files")}

    def test_a_plural_group_that_is_complete_is_not_translated_again(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        done = {
            "variations": {
                "plural": {"one": _su("%d fichier"), "many": _su("%d de fichiers"), "other": _su("%d fichiers")}
            }
        }
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural, "fr": done}}}))

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_only_the_missing_categories_of_a_plural_group_are_translated(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        partial = {"variations": {"plural": {"one": _su("%d fichier"), "other": _su("", state="new")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural, "fr": partial}}}))

        result = _translate(parser, source, "fr", source)

        assert result["strings"]["files"]["localizations"]["fr"]["variations"]["plural"] == {
            "one": _su("%d fichier"),
            "other": _mt("[fr] %d files"),
            "many": _mt("[fr] %d files"),
        }

    def test_a_zero_category_of_the_source_is_kept_in_every_target(self, parser, write_catalog):
        plural = {"variations": {"plural": {"zero": _su("No files"), "one": _su("%d file"), "other": _su("%d files")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural}}}))

        result = _translate(parser, source, "ja", source)

        assert set(result["strings"]["files"]["localizations"]["ja"]["variations"]["plural"]) == {"zero", "other"}

    def test_a_target_the_translator_made_vary_by_plural_is_left_alone(self, parser, write_catalog):
        varied = {"variations": {"plural": {"one": _su("Un fichier"), "other": _su("Des fichiers")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": _su("Files"), "fr": varied}}}))

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_translated_plain_target_of_a_plural_source_is_left_alone(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural, "fr": _su("%d fichier(s)")}}}))

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_plain_target_to_review_is_replaced_by_the_plural_group_of_the_source(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        review = _su("%d fichiers", state="needs_review")
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural, "fr": review}}}))

        result = _translate(parser, source, "fr", source)

        fr = result["strings"]["files"]["localizations"]["fr"]
        assert "stringUnit" not in fr
        assert set(fr["variations"]["plural"]) == {"one", "many", "other"}

    def test_a_translated_value_with_a_missing_substitution_gets_the_substitution(self, parser, write_catalog):
        substitution = {"argNum": 1, "variations": {"plural": {"other": _su("%arg files")}}}
        en = {**_su("%#@files@ left"), "substitutions": {"files": substitution}}
        source = write_catalog(_catalog({"left": {"localizations": {"en": en, "fr": _su("%#@files@ restants")}}}))

        result = _translate(parser, source, "fr", source)

        fr = result["strings"]["left"]["localizations"]["fr"]
        assert fr["stringUnit"] == _su("%#@files@ restants")["stringUnit"]
        assert fr["substitutions"]["files"]["variations"]["plural"]["other"] == _mt("[fr] %arg files")

    def test_device_variations_are_translated_each(self, parser, write_catalog):
        device = {"variations": {"device": {"iphone": _su("Tap"), "mac": _su("Click")}}}
        source = write_catalog(_catalog({"action": {"localizations": {"en": device}}}))

        result = _translate(parser, source, "fr", source)

        assert result["strings"]["action"]["localizations"]["fr"]["variations"]["device"] == {
            "iphone": _mt("[fr] Tap"),
            "mac": _mt("[fr] Click"),
        }

    def test_only_the_missing_devices_are_translated(self, parser, write_catalog):
        en = {"variations": {"device": {"iphone": _su("Tap"), "mac": _su("Click")}}}
        fr = {"variations": {"device": {"iphone": _su("Touchez")}}}
        source = write_catalog(_catalog({"action": {"localizations": {"en": en, "fr": fr}}}))

        assert [u.key for u in parser.clone(parser.parse(source, []), "fr").units] == ["action[mac]"]

        result = _translate(parser, source, "fr", source)

        assert result["strings"]["action"]["localizations"]["fr"]["variations"]["device"] == {
            "iphone": _su("Touchez"),
            "mac": _mt("[fr] Click"),
        }

    def test_the_devices_of_a_variation_are_written_sorted(self, parser, write_catalog):
        device = {"variations": {"device": {"mac": _su("Click"), "iphone": _su("Tap")}}}
        source = write_catalog(_catalog({"action": {"localizations": {"en": device}}}))

        result = _translate(parser, source, "fr", source)

        assert list(result["strings"]["action"]["localizations"]["fr"]["variations"]["device"]) == ["iphone", "mac"]

    def test_a_device_can_vary_by_plural(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        device = {"variations": {"device": {"iphone": plural, "mac": _su("Files")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": device}}}))

        cloned = parser.clone(parser.parse(source, []), "ru")
        assert [u.key for u in cloned.units] == [
            "files[iphone.one]",
            "files[iphone.few]",
            "files[iphone.many]",
            "files[iphone.other]",
            "files[mac]",
        ]

        result = _translate(parser, source, "ru", source)

        ru = result["strings"]["files"]["localizations"]["ru"]["variations"]["device"]
        assert ru["mac"] == _mt("[ru] Files")
        assert ru["iphone"]["variations"]["plural"] == {
            "few": _mt("[ru] %d files"),
            "many": _mt("[ru] %d files"),
            "one": _mt("[ru] %d file"),
            "other": _mt("[ru] %d files"),
        }

    def test_a_translated_plain_target_of_a_device_source_is_left_alone(self, parser, write_catalog):
        device = {"variations": {"device": {"iphone": _su("Tap")}}}
        source = write_catalog(_catalog({"action": {"localizations": {"en": device, "fr": _su("Touchez")}}}))

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_target_the_translator_made_vary_by_plural_is_left_alone_for_a_device_source(self, parser, write_catalog):
        device = {"variations": {"device": {"iphone": _su("Tap")}}}
        plural = {"variations": {"plural": {"one": _su("Un"), "other": _su("Des")}}}
        source = write_catalog(_catalog({"action": {"localizations": {"en": device, "fr": plural}}}))

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_plain_target_to_review_is_replaced_by_the_device_variations_of_the_source(self, parser, write_catalog):
        device = {"variations": {"device": {"iphone": _su("Tap")}}}
        review = _su("Touchez", state="needs_review")
        source = write_catalog(_catalog({"action": {"localizations": {"en": device, "fr": review}}}))

        result = _translate(parser, source, "fr", source)

        fr = result["strings"]["action"]["localizations"]["fr"]
        assert "stringUnit" not in fr
        assert fr["variations"]["device"] == {"iphone": _mt("[fr] Tap")}

    def test_a_substitution_inside_a_device_keeps_its_argument_fields(self, parser, write_catalog):
        substitution = {
            "argNum": 1,
            "formatSpecifier": "lld",
            "variations": {"plural": {"one": _su("%arg file"), "other": _su("%arg files")}},
        }
        iphone = {**_su("%#@files@ left"), "substitutions": {"files": substitution}}
        device = {"variations": {"device": {"iphone": iphone}}}
        source = write_catalog(_catalog({"left": {"localizations": {"en": device}}}))

        result = _translate(parser, source, "fr", source)

        fr = result["strings"]["left"]["localizations"]["fr"]["variations"]["device"]["iphone"]
        assert fr["stringUnit"]["value"] == "[fr] %#@files@ left"
        assert fr["substitutions"]["files"]["argNum"] == 1
        assert fr["substitutions"]["files"]["formatSpecifier"] == "lld"
        assert fr["substitutions"]["files"]["variations"]["plural"]["other"] == _mt("[fr] %arg files")

    def test_a_level_that_mixes_plural_and_device_variations_is_skipped_with_a_warning(
        self, parser, write_catalog, caplog
    ):
        mixed = {"variations": {"plural": {"other": _su("%d files")}, "device": {"mac": _su("Files")}}}
        source = write_catalog(_catalog({"mixed": {"localizations": {"en": mixed}}, "fine": {}}))

        with caplog.at_level(logging.WARNING):
            units = parser.clone(parser.parse(source, []), "fr").units

        assert [u.key for u in units] == ["fine"]
        assert any("mixed" in r.message for r in caplog.records)

    def test_substitutions_keep_their_argument_fields(self, parser, write_catalog):
        localization = {
            **_su("%#@files@ left"),
            "substitutions": {
                "files": {
                    "argNum": 1,
                    "formatSpecifier": "lld",
                    "variations": {"plural": {"one": _su("%arg file"), "other": _su("%arg files")}},
                }
            },
        }
        source = write_catalog(_catalog({"left": {"localizations": {"en": localization}}}))

        result = _translate(parser, source, "fr", source)

        fr = result["strings"]["left"]["localizations"]["fr"]
        assert fr["stringUnit"]["value"] == "[fr] %#@files@ left"
        assert fr["substitutions"]["files"]["argNum"] == 1
        assert fr["substitutions"]["files"]["formatSpecifier"] == "lld"
        assert fr["substitutions"]["files"]["variations"]["plural"]["other"] == _mt("[fr] %arg files")

    def test_a_translation_waiting_for_review_is_not_translated_again_while_its_source_is_the_same(
        self, parser, write_catalog
    ):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        _remember(parser, source, "fr")

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_a_translation_waiting_for_review_is_translated_again_when_its_source_changed(
        self, parser, write_catalog
    ):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        _remember(parser, source, "fr")
        _set_source(source, "greeting", "Hi")

        units = parser.clone(parser.parse(source, []), "fr").units

        assert [(u.key, u.source_text) for u in units] == [("greeting", "Hi")]

    def test_an_approved_translation_is_kept_while_its_source_is_the_same(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        _remember(parser, source, "fr")
        _approve(source, "greeting", "fr")

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_an_approved_translation_is_translated_again_when_its_source_changed(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        _remember(parser, source, "fr")
        _approve(source, "greeting", "fr")
        _set_source(source, "greeting", "Hi")

        result = _translate(parser, source, "fr", source)

        assert result["strings"]["greeting"]["localizations"]["fr"] == _mt("[fr] Hi")

    def test_a_translation_without_a_record_is_kept_whatever_its_source(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hi"), "fr": _su("Bonjour")}}}))

        assert parser.clone(parser.parse(source, []), "fr").units == []

    def test_each_plural_category_is_recorded_on_its_own(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        source = write_catalog(_catalog({"files": {"localizations": {"en": plural}}}))

        recorded = _remember(parser, source, "ru")

        assert set(recorded) == {"files[one]", "files[few]", "files[many]", "files[other]"}
        assert parser.clone(parser.parse(source, []), "ru").units == []

    def test_the_record_keeps_units_left_alone_and_drops_units_no_longer_in_the_source(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        recorded = _remember(parser, source, "fr")
        parser.use_translated_from(lambda path, locale: {**recorded, "gone": "0123456789abcdef"})

        cloned = parser.clone(parser.parse(source, []), "fr")

        assert cloned.translated_from == recorded

    def test_the_record_is_looked_up_by_source_path_and_locale(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {}}))
        asked = []
        parser.use_translated_from(lambda path, locale: asked.append((path, locale)) or {})

        parser.clone(parser.parse(source, []), "fr")

        assert asked == [(str(source), "fr")]

    def test_a_unit_that_was_not_written_back_leaves_the_target_absent(self, parser, write_catalog):
        source = write_catalog(_catalog({"a": {}, "b": {}}))
        cloned = parser.clone(parser.parse(source, []), "fr")

        next(u for u in cloned.units if u.key == "a").write_back("A")
        cloned.save(source)

        strings = json.loads(source.read_text(encoding="utf-8"))["strings"]
        assert "fr" in strings["a"]["localizations"]
        assert "localizations" not in strings["b"]

    def test_saving_one_locale_keeps_what_another_locale_wrote_meanwhile(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        parsed = parser.parse(source, [])
        fr, de = parser.clone(parsed, "fr"), parser.clone(parsed, "de")
        fr.units[0].write_back("Bonjour")
        de.units[0].write_back("Hallo")

        fr.save(source)
        de.save(source)

        assert set(json.loads(source.read_text(encoding="utf-8"))["strings"]["greeting"]["localizations"]) == {
            "en",
            "fr",
            "de",
        }

    def test_localizations_are_sorted_and_the_file_uses_xcodes_layout(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello"), "de": _su("Hallo")}}}))

        _translate(parser, source, "fr", source)

        text = source.read_text(encoding="utf-8")
        assert '"greeting" : {' in text
        assert list(json.loads(text)["strings"]["greeting"]["localizations"]) == ["de", "en", "fr"]

    def test_existing_keys_keep_their_order_and_new_plural_categories_are_sorted(self, parser, write_catalog):
        plural = {"variations": {"plural": {"one": _su("%d file"), "other": _su("%d files")}}}
        entry = {"shouldTranslate": True, "comment": "Count", "localizations": {"en": plural}}
        source = write_catalog(_catalog({"files": entry}))

        result = _translate(parser, source, "ru", source)

        assert list(result["strings"]["files"]) == ["shouldTranslate", "comment", "localizations"]
        ru = result["strings"]["files"]["localizations"]["ru"]["variations"]["plural"]
        assert list(ru) == ["few", "many", "one", "other"]

    def test_non_ascii_characters_are_written_as_they_are(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {}}))

        _translate(parser, source, "fr", source, transform=lambda text: "Bonjour é")

        assert "Bonjour é" in source.read_text(encoding="utf-8")

    def test_a_target_that_is_the_source_language_is_skipped_with_a_warning(self, parser, write_catalog, caplog):
        source = write_catalog(_catalog({"greeting": {}}, source="en"))

        with caplog.at_level(logging.WARNING):
            units = parser.clone(parser.parse(source, []), "EN").units

        assert units == []
        assert any("source language" in r.message for r in caplog.records)

    def test_malformed_strings_are_skipped_instead_of_failing_the_file(self, parser, write_catalog):
        source = write_catalog(
            _catalog(
                {
                    "not an object": "oops",
                    "number value": {"localizations": {"en": {"stringUnit": {"value": 3}}}},
                    "odd comment": {"comment": ["a"], "localizations": "oops"},
                    "fine": {},
                }
            )
        )

        units = parser.clone(parser.parse(source, []), "fr").units

        # A source value that isn't text has nothing to translate.
        assert [u.key for u in units] == ["odd comment", "fine"]
        assert all(u.context_hint is None for u in units)

    def test_raises_value_error_when_the_file_is_not_utf8(self, parser, tmp_path):
        source = tmp_path / "Localizable.xcstrings"
        source.write_bytes('{"sourceLanguage": "en", "strings": {"é": {}}}'.encode("latin-1"))

        with pytest.raises(ValueError, match="UTF-8"):
            parser.parse(source, [])

    def test_slashes_are_escaped_and_the_file_ends_with_a_newline(self, parser, tmp_path):
        source = tmp_path / "Localizable.xcstrings"
        source.write_text('{"sourceLanguage" : "en", "strings" : {"a\\/b" : {}}}', encoding="utf-8")

        _translate(parser, source, "fr", source, transform=lambda text: "c/d")

        text = source.read_text(encoding="utf-8")
        assert '"a\\/b"' in text
        assert '"c\\/d"' in text
        assert text.endswith("}\n")
        assert json.loads(text)["strings"]["a/b"]["localizations"]["fr"] == _mt("c/d")

    def test_saving_without_translations_leaves_the_existing_file_untouched(self, parser, tmp_path):
        source = tmp_path / "Localizable.xcstrings"
        original = '{"sourceLanguage":"en","strings":{"greeting":{}}}'
        source.write_text(original, encoding="utf-8")

        parser.clone(parser.parse(source, []), "fr").save(source)

        assert source.read_text(encoding="utf-8") == original

    def test_saving_a_catalog_that_was_not_cloned_for_a_locale_raises(self, parser, write_catalog, tmp_path):
        source = write_catalog(_catalog({"greeting": {}}))

        with pytest.raises(ValueError, match="clone it"):
            parser.parse(source, []).save(tmp_path / "out.xcstrings")

    def test_clone_write_back_does_not_touch_the_parsed_catalog(self, parser, write_catalog, tmp_path):
        source = write_catalog(_catalog({"greeting": {}}))
        parsed = parser.parse(source, [])

        cloned = parser.clone(parsed, "fr")
        cloned.units[0].write_back("Bonjour")
        cloned.save(tmp_path / "out.xcstrings")

        assert "localizations" not in parsed.document["strings"]["greeting"]


class TestXcstringsParserSharedFile:
    def test_content_hash_ignores_targets_and_changes_with_the_source(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        before = parser.content_hash(source)

        _translate(parser, source, "fr", source)
        assert parser.content_hash(source) == before

        write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hi")}}}))
        assert parser.content_hash(source) != before

    def test_has_target_sees_what_a_save_wrote(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"en": _su("Hello")}}}))
        assert not parser.has_target(source, source, "fr", [])

        _remember(parser, source, "fr")

        assert parser.has_target(source, source, "fr", [])

    def test_has_target_is_false_for_a_translation_waiting_for_review_without_a_record(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"localizations": {"fr": _mt("Bonjour")}}}))

        assert not parser.has_target(source, source, "fr", [])

    def test_content_hash_changes_with_the_comment_sent_as_context(self, parser, write_catalog):
        source = write_catalog(_catalog({"greeting": {"comment": "Home"}}))
        before = parser.content_hash(source)

        write_catalog(_catalog({"greeting": {"comment": "Settings"}}))

        assert parser.content_hash(source) != before
