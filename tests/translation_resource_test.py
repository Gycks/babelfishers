from pathlib import Path

import pytest

from babelfishers.models.engine import Engine
from babelfishers.models.translation_resource import (
    ResourcePath,
    TranslationResource,
    TranslationResourceType,
)


@pytest.fixture
def make_file(tmp_path):
    def _make(relative_path: str, content: str = "{}"):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    return _make


class TestTranslationResourceValidation:
    def test_raises_value_error_when_resource_type_is_invalid(self):
        with pytest.raises(ValueError, match="Invalid resource type"):
            TranslationResource.load("en", "not-a-real-type", {"paths": []})

    def test_raises_type_error_when_entry_is_malformed(self):
        with pytest.raises(TypeError, match="malformed"):
            TranslationResource.load("en", "json", {"paths": [123]})

    def test_loads_direct_path_given_as_plain_string(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")

        data = {"paths": ["messages_en.json"]}
        resources = TranslationResource.load("en", "json", data)

        assert len(resources) == 1
        resource = resources[0]
        assert resource.resource_type == TranslationResourceType.JSON
        assert resource.engine is None
        assert resource.excluded_keys == []
        assert [p.path for p in resource.paths] == [Path("messages_en.json")]

    def test_substitutes_source_placeholder_in_path(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("locales/en/messages.json")

        data = {"paths": ["locales/[source]/messages.json"]}
        resources = TranslationResource.load("en", "json", data)

        assert [p.path for p in resources[0].paths] == [Path("locales/en/messages.json")]

    def test_glob_pattern_matches_multiple_files(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("locales/en/a.json")
        make_file("locales/en/b.json")

        data = {"paths": ["locales/[source]/*.json"]}
        resources = TranslationResource.load("en", "json", data)

        found_paths = {p.path for p in resources[0].paths}
        assert found_paths == {Path("locales/en/a.json"), Path("locales/en/b.json")}

    def test_loads_path_from_dict_entry(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")

        data = {"paths": [{"path": "messages_en.json"}]}
        resources = TranslationResource.load("en", "json", data)

        assert [p.path for p in resources[0].paths] == [Path("messages_en.json")]

    def test_excludes_files_matching_exclude_pattern(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("locales/en/a.json")
        make_file("locales/en/b.json")

        data = {
            "paths": [
                {
                    "path": "locales/[source]/*.json",
                    "exclude": ["locales/[source]/b.json"],
                }
            ]
        }
        resources = TranslationResource.load("en", "json", data)

        found_paths = {p.path for p in resources[0].paths}
        assert found_paths == {Path("locales/en/a.json")}

    def test_carries_excluded_keys_through_from_dict_entry(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")

        data = {"paths": [{"path": "messages_en.json", "excluded_keys": ["debug", "internal"]}]}
        resources = TranslationResource.load("en", "json", data)

        assert resources[0].excluded_keys == ["debug", "internal"]

    def test_attaches_engine_when_valid_engine_given(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")

        data = {"paths": [{"path": "messages_en.json", "engine": "deepl"}]}
        resources = TranslationResource.load("en", "json", data)

        assert resources[0].engine == Engine.DeepL

    def test_engine_is_none_when_no_engine_given(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")

        data = {"paths": [{"path": "messages_en.json"}]}
        resources = TranslationResource.load("en", "json", data)

        assert resources[0].engine is None

    def test_engine_is_none_when_engine_name_is_invalid(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")

        data = {"paths": [{"path": "messages_en.json", "engine": "not-a-real-engine"}]}
        resources = TranslationResource.load("en", "json", data)

        assert resources[0].engine is None

    def test_each_entry_produces_a_separate_resource(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("a.json")
        make_file("b.json")

        data = {"paths": ["a.json", "b.json"]}
        resources = TranslationResource.load("en", "json", data)

        assert len(resources) == 2

    def test_returns_empty_list_when_data_is_none(self):
        assert TranslationResource.batch_load("en", None) == []

    def test_loads_resources_across_multiple_resource_types(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("messages_en.json")
        make_file("index_en.html")

        data = {
            "json": {"paths": ["messages_en.json"]},
            "html": {"paths": ["index_en.html"]},
        }
        resources = TranslationResource.batch_load("en", data)

        types_found = {r.resource_type for r in resources}
        assert types_found == {TranslationResourceType.JSON, TranslationResourceType.HTML}

    def test_substitutes_source_placeholder_for_target_locale(self):
        resource_path = ResourcePath(
            path=Path("locales/en/messages.json"),
            pattern="locales/[source]/messages.json",
        )
        assert resource_path.get_destination_path("fr") == Path("locales/fr/messages.json")

    def test_falls_back_to_appending_locale_suffix_when_no_placeholder(self):
        resource_path = ResourcePath(path=Path("messages_en.json"), pattern="messages_en.json")
        assert resource_path.get_destination_path("fr") == Path("messages_en_fr.json")

    def test_direct_path_without_placeholder_appends_rather_than_replaces_locale(self):
        resource_path = ResourcePath(path=Path("messages_en.json"), pattern="messages_en.json")
        assert resource_path.get_destination_path("fr") == Path("messages_en_fr.json")

    def test_filename_with_multiple_dots_only_strips_last_suffix(self):
        resource_path = ResourcePath(path=Path("archive.tar.gz"), pattern="archive.tar.gz")
        assert resource_path.get_destination_path("fr") == Path("archive.tar_fr.gz")

    def test_path_with_no_suffix_at_all(self):
        resource_path = ResourcePath(path=Path("messages"), pattern="messages")
        assert resource_path.get_destination_path("fr") == Path("messages_fr")

    def test_raises_value_error_when_dict_entry_is_missing_path(self):
        data = {"paths": [{"exclude": []}]}
        with pytest.raises(ValueError, match="malformed"):
            TranslationResource.load("en", "json", data)

    def test_raises_no_error_when_exclude_is_explicitly_none(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("a.json")
        data = {"paths": [{"path": "a.json", "exclude": None}]}
        resources = TranslationResource.load("en", "json", data)
        assert len(resources) == 1

    def test_raises_no_error_when_excluded_keys_is_explicitly_none(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("a.json")
        data = {"paths": [{"path": "a.json", "excluded_keys": None}]}
        resources = TranslationResource.load("en", "json", data)
        assert len(resources) == 1

    def test_raises_value_error_when_key_name_absent(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("a.json")
        data = {"literally_anything": ["a.json"]}
        with pytest.raises(ValueError, match="malformed"):
            TranslationResource.load("en", "json", data)

    def test_raises_value_error_when_multiple_keys_present(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("a.json")
        make_file("b.json")
        data = {"paths": ["a.json"], "typo_key": ["b.json"]}
        with pytest.raises(ValueError, match="malformed"):
            TranslationResource.load("en", "json", data)

    def test_returns_empty_list_when_data_has_no_keys(self):
        assert TranslationResource.load("en", "json", {}) == []

    def test_returns_resource_with_empty_paths_when_glob_matches_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        data = {"paths": ["does_not_exist_*.json"]}
        resources = TranslationResource.load("en", "json", data)
        assert resources[0].paths == []

    def test_recursive_glob_matches_nested_subdirectories(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("locales/en/nested/a.json")
        data = {"paths": ["locales/[source]/**/*.json"]}
        resources = TranslationResource.load("en", "json", data)
        assert [p.path for p in resources[0].paths] == [Path("locales/en/nested/a.json")]

    def test_pattern_retains_source_placeholder_for_later_locale_substitution(self, tmp_path, monkeypatch, make_file):
        monkeypatch.chdir(tmp_path)
        make_file("locales/en/messages.json")
        data = {"paths": ["locales/[source]/*.json"]}
        resources = TranslationResource.load("en", "json", data)
        resource_path = resources[0].paths[0]
        assert resource_path.pattern == "locales/[source]/messages.json"
        assert resource_path.get_destination_path("fr") == Path("locales/fr/messages.json")

    def test_validate_is_not_case_sensitive(self):
        assert TranslationResourceType.validate("json") == TranslationResourceType.JSON
        assert TranslationResourceType.validate("JSON") == TranslationResourceType.JSON
