import pytest

from babelfishers.models.engine import Engine


class TestEngineValidation:
    def test_validate_returns_engine_when_valid_name(self):
        for engine in Engine:
            assert Engine.validate(engine.value) == engine

        for engine in Engine:
            assert Engine.validate(engine.value.upper()) == engine

    @pytest.mark.parametrize("invalid_name", [
        "not-a-real-engine",
        "deepl-v2",
        "",
    ])
    def test_validate_returns_none_when_invalid_name(self, invalid_name):
        assert invalid_name not in {engine.value for engine in Engine}
        assert Engine.validate(invalid_name) is None
