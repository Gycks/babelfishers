import re

from babelfishers.models.translation_resource import TranslationResourceType


# Rails / gettext-style: %{name}
_RAILS_NAMED = re.compile(r"%\{[A-Za-z_][\w.]*\}")

# Symfony / Twig-style: %name%
_SYMFONY_PERCENT = re.compile(r"%[A-Za-z_][\w.]*%")

# Python %-formatting (Django .po sources): %(name)s, %(count)d
_PYTHON_PERCENT_NAMED = re.compile(r"%\([A-Za-z_]\w*\)[sd]")

# printf/sprintf family: C, Java String.format, Android, generic %s/%d,
# positional %1$s, iOS %@ / %1$@, long forms %ld/%lld/%lu
_PRINTF = re.compile(r"%(?:\d+\$)?[-+ 0#]*\d*(?:\.\d+)?(?:[sdifFeEgGxXo@]|ld|lld|lu)")

# Apple .xcstrings substitution literal + stringsdict-style specifier ref
_XCSTRINGS_ARG = re.compile(r"%arg\b")
_STRINGSDICT_SPECIFIER = re.compile(r"%(?:\d+\$)?#@[A-Za-z_]\w*@")

# Inline XML markup embedded in a source string's mixed content, e.g. Android's
# <xliff:g id="count">%d</xliff:g> or XLIFF's <g>/<x/>/<bpt>/<ept>/<ph>. Must
# be passed through untranslated so the surrounding structure survives.
_INLINE_XML_TAG_PAIR = re.compile(r"<([\w:.-]+)(?:\s[^>]*)?>.*?</\1>", re.DOTALL)
_INLINE_XML_SELF_CLOSING_TAG = re.compile(r"<[\w:.-]+(?:\s[^>]*)?/>")


FORMAT_CATEGORIES: dict[TranslationResourceType, list[re.Pattern[str]]] = {
    TranslationResourceType.HTML: [],
    TranslationResourceType.JSON: [_PRINTF],
    TranslationResourceType.YAML: [_RAILS_NAMED, _SYMFONY_PERCENT],
    TranslationResourceType.JAVA_PROPERTIES: [_PRINTF],
    TranslationResourceType.ANDROID_STRINGS: [_INLINE_XML_TAG_PAIR, _INLINE_XML_SELF_CLOSING_TAG, _PRINTF],
    TranslationResourceType.GETTEXT: [_PRINTF, _PYTHON_PERCENT_NAMED],
    TranslationResourceType.APPLE_STRINGS: [_PRINTF, _XCSTRINGS_ARG, _STRINGSDICT_SPECIFIER],
    TranslationResourceType.FLUTTER_ARB: [],
    TranslationResourceType.XLIFF: [_INLINE_XML_TAG_PAIR, _INLINE_XML_SELF_CLOSING_TAG, _PRINTF],
    TranslationResourceType.DOTNET_RESX: [],
}
