from collections.abc import Callable

import pytest

from babelfishers.models.translation_resource import TranslationResourceType
from babelfishers.models.translations import TranslationUnit


@pytest.fixture
def make_unit() -> Callable[..., tuple[TranslationUnit, dict]]:
    def _make(
        source_text: str,
        key: str = "k1",
        context_hint: str | None = None,
        skip_translation: bool = False,
    ) -> tuple[TranslationUnit, dict]:
        written: dict = {}
        unit = TranslationUnit(
            unit_type=TranslationResourceType.JSON,
            key=key,
            source_text=source_text,
            write_back=lambda v, key=key: written.__setitem__(key, v),
            context_hint=context_hint,
            skip_translation=skip_translation,
        )
        return unit, written

    return _make
