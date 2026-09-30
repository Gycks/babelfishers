from babel import Locale, UnknownLocaleError


# Locales Babel has no data for, mapped to one with the same plural rules.
_PLURAL_RULES_OF: dict[str, str] = {"prs": "fa_AF"}


def babel_locale_id(locale: str) -> str:
    """
    The identifier Babel reads `locale` as. Babel separates subtags with an
    underscore and rejects a hyphenated code such as `pt-BR`.
    """
    identifier = locale.replace("-", "_")
    return _PLURAL_RULES_OF.get(identifier, identifier)


def required_plural_categories(locale: str) -> set[str]:
    """
    The CLDR plural categories a translation for `locale` must cover for a
    plural group to render correctly for every possible count. "other" is
    always required — it's CLDR's mandatory catch-all and isn't itemized in
    a locale's own rule set.
    """
    try:
        tags = set(Locale.parse(babel_locale_id(locale)).plural_form.tags)
    except (UnknownLocaleError, ValueError):
        return {"other"}

    return tags | {"other"}
