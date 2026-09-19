import json
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


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "locales/en/messages.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"greeting": "Hello"}), encoding="utf-8")
    (tmp_path / "babelfishers.toml").write_text(
        '[locale]\nsource = "en"\ntargets = ["fr", "de"]\n\n'
        '[engine]\nprovider = "deepl"\n\n'
        '[resources.json]\npaths = ["locales/[source]/messages.json"]\n',
        encoding="utf-8",
    )
    return tmp_path
