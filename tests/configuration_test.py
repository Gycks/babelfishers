import pytest

from babelfishers.models.app_config import AppConfig
from babelfishers.core.supported_cultures import SUPPORTED_CULTURES, is_supported_by
from babelfishers.models.engine import Engine


@pytest.fixture
def write_config(tmp_path):
    def _write(content: str, filename: str = "config.toml"):
        path = tmp_path / filename
        path.write_text(content)
        return path

    return _write


class TestAppConfigLoadFileValidation:
    def test_raises_file_not_found_when_file_does_not_exist(self, tmp_path):
        missing_file = tmp_path / "non_existent_config.toml"
        with pytest.raises(FileNotFoundError):
            AppConfig.load(missing_file)

    @pytest.mark.parametrize("filename", [
        "invalid_config.txt",
        "invalid_config.json",
        "invalid_config.yaml",
        "invalid_config",  # no extension at all
    ])
    def test_raises_value_error_when_file_extension_is_not_toml(self, tmp_path, filename):
        invalid_file = tmp_path / filename
        invalid_file.write_text("some content")
        with pytest.raises(ValueError, match="valid TOML file"):
            AppConfig.load(invalid_file)

    def test_raises_value_error_when_locale_section_is_missing(self, write_config):
        config_file = write_config(
            """
            [engine]
            provider = "deepl"
            """
        )
        with pytest.raises(ValueError, match="valid section named locale"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_source_locale_is_missing(self, write_config):
        config_file = write_config(
            """
            [locale]
            targets = ["en"]
            
            [engine]
            provider = "deepl"
            """
        )
        with pytest.raises(ValueError, match="Source locale"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_source_locale_is_not_supported(self, write_config):
        config_file = write_config(
            """
            [locale]
            source = "zz-ZZ"
            targets = ["fr"]
            
            [engine]
            provider = "deepl"
            """
        )
        with pytest.raises(ValueError, match="Source locale zz-ZZ"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_target_locales_are_missing(self, write_config):
        config_file = write_config(
            """
            [locale]
            source = "en"
            
            [engine]
            provider = "deepl"
            """
        )
        with pytest.raises(ValueError, match="Target locales"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_target_locales_are_empty(self, write_config):
        config_file = write_config(
            """
            [locale]
            source = "en"
            targets = []
            
            [engine]
            provider = "deepl"
            """
        )
        with pytest.raises(ValueError, match="Target locales"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_target_locales_are_not_supported(self, write_config):
        config_file = write_config(
            """
            [locale]
            source = "en"
            targets = ["zz-ZZ"]
            
            [engine]
            provider = "deepl"
            """
        )
        with pytest.raises(ValueError, match="Target locales"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_engine_section_is_missing(self, write_config):
        config_file = write_config(
            """
            [locale]
            source = "en"
            targets = ["fr"]
            """
        )
        with pytest.raises(ValueError, match="engine"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_engine_provider_is_missing(self, write_config):
        config_file = write_config(
            """
            [locale]
            source = "en"
            targets = ["fr"]
            
            [engine]
            """
        )
        with pytest.raises(ValueError, match="Engine provider"):
            AppConfig.load(config_file)

    def test_raises_value_error_when_engine_provider_is_not_supported(self, write_config, monkeypatch):
        config_file = write_config(
            """
            [locale]
            source = "en"
            targets = ["fr"]
            
            [engine]
            provider = "not-a-real-engine"
            """
        )
        with pytest.raises(ValueError, match="not-a-real-engine is not supported"):
            AppConfig.load(config_file)

    def test_loads_valid_configuration(self, write_config):
        deepl_targets = [
            code
            for code, culture in SUPPORTED_CULTURES.items()
            if culture.default_variant is None and code != "en-US" and is_supported_by(code, Engine.DeepL)
        ]
        config_file = write_config(
            f"""
            [locale]
            source = "en"
            targets = {deepl_targets}
            
            [engine]
            provider = "deepl"
            """
        )
        config = AppConfig.load(config_file)
        assert config.source_locale == "en"
        assert sorted(config.target_locales) == sorted(deepl_targets)
        assert config.translation_engine.value == "deepl"

    def test_raises_value_error_when_toml_syntax_is_malformed(self, write_config):
        config_file = write_config("""
            [locale
            source = "en"
            """)
        with pytest.raises(ValueError) as exc_info:
            AppConfig.load(config_file)
        assert "valid TOML file" not in str(exc_info.value)

    def test_rejects_source_locale_duplicated_in_targets(self, write_config):
        config_file = write_config("""
            [locale]
            source = "en"
            targets = ["en", "fr"]

            [engine]
            provider = "deepl"
            """)
        config = AppConfig.load(config_file)
        assert config.target_locales == ["fr"]

    def test_rejects_duplicate_repeated_target_locales(self, write_config):
        config_file = write_config("""
            [locale]
            source = "en"
            targets = ["fr", "fr"]

            [engine]
            provider = "deepl"
            """)
        config = AppConfig.load(config_file)
        assert config.target_locales == ["fr"]

    def test_targets_given_as_plain_string_fails_for_the_wrong_reason(self, write_config):
        config_file = write_config("""
            [locale]
            source = "en"
            targets = "fr"

            [engine]
            provider = "deepl"
            """)
        with pytest.raises(ValueError, match="Target locales is malformed"):
            AppConfig.load(config_file)

    def test_source_locale_is_not_trimmed_or_normalized(self, write_config):
        config_file = write_config("""
            [locale]
            source = " en"
            targets = ["fr"]

            [engine]
            provider = "deepl"
            """)
        with pytest.raises(ValueError, match="Source locale"):
            AppConfig.load(config_file)

    def test_locale_codes_are_matched_whatever_their_case(self, write_config):
        config_file = write_config("""
            [locale]
            source = "EN-us"
            targets = ["pt-br", "zh-hant"]

            [engine]
            provider = "deepl"
            """)
        config = AppConfig.load(config_file)
        assert config.source_locale == "en-US"
        assert sorted(config.target_locales) == ["pt-BR", "zh-Hant"]

    def test_target_that_is_the_source_under_its_plain_code_is_dropped(self, write_config):
        config_file = write_config("""
            [locale]
            source = "en"
            targets = ["en-US", "fr"]

            [engine]
            provider = "deepl"
            """)
        config = AppConfig.load(config_file)
        assert config.target_locales == ["fr"]

    def test_rejects_targets_that_are_all_the_source_locale(self, write_config):
        config_file = write_config("""
            [locale]
            source = "pt"
            targets = ["pt-PT", "PT"]

            [engine]
            provider = "deepl"
            """)
        with pytest.raises(ValueError, match="Target locales not set. Every target is the source locale pt"):
            AppConfig.load(config_file)

    def test_rejects_a_plain_code_next_to_its_default_variant(self, write_config):
        config_file = write_config("""
            [locale]
            source = "en"
            targets = ["pt", "pt-PT"]

            [engine]
            provider = "deepl"
            """)
        with pytest.raises(ValueError, match=r"pt and pt-PT are both Portuguese \(Portugal\)"):
            AppConfig.load(config_file)

    @pytest.mark.parametrize(
        ("provider", "source", "targets", "unsupported"),
        [
            ("deepl", "en", ["fr", "am"], "am"),
            ("libre-translate", "af", ["fr"], "af"),
            ("azure", "en", ["en-GB", "de"], "en-GB"),
            ("google-translate", "en", ["prs"], "prs"),
        ],
    )
    def test_rejects_locales_the_engine_does_not_support(self, write_config, provider, source, targets, unsupported):
        config_file = write_config(f"""
            [locale]
            source = "{source}"
            targets = {targets}

            [engine]
            provider = "{provider}"
            """)
        with pytest.raises(ValueError, match=f"engine {provider} does not support the locale\\(s\\) {unsupported}\\."):
            AppConfig.load(config_file)

    def test_ai_providers_support_every_locale(self, write_config):
        config_file = write_config("""
            [locale]
            source = "en-GB"
            targets = ["am", "wo", "sr-Latn"]

            [engine]
            provider = "anthropic"
            """)
        config = AppConfig.load(config_file)
        assert sorted(config.target_locales) == ["am", "sr-Latn", "wo"]

    def test_rejects_locales_the_engine_of_a_resource_does_not_support(self, write_config, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "en.json").write_text("{}")
        config_file = write_config("""
            [locale]
            source = "en"
            targets = ["am"]

            [engine]
            provider = "anthropic"

            [resources.json]
            paths = [{ path = "[source].json", engine = "deepl" }]
            """)
        with pytest.raises(ValueError, match=r"engine deepl \(set on a \[resources.json\] path\) does not support"):
            AppConfig.load(config_file)
