import pytest

from babelfishers.models.app_config import AppConfig
from babelfishers.core.supported_cultures import SUPPORTED_CULTURES


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
        with pytest.raises(ValueError, match="Targets locale"):
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
        config_file = write_config(
            f"""
            [locale]
            source = "en"
            targets = {[key for key in SUPPORTED_CULTURES.keys() if key != "en"]} 
            
            [engine]
            provider = "deepl"
            """
        )
        config = AppConfig.load(config_file)
        assert config.source_locale == "en"
        assert sorted(config.target_locales) == sorted([key for key in SUPPORTED_CULTURES.keys() if key != "en"])
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
        with pytest.raises(ValueError, match="Targets locale is malformed"):
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
