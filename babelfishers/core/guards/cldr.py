from babel import Locale, UnknownLocaleError


def required_plural_categories(locale: str) -> set[str]:
    """
    The CLDR plural categories a translation for `locale` must cover for a
    plural group to render correctly for every possible count. "other" is
    always required — it's CLDR's mandatory catch-all and isn't itemized in
    a locale's own rule set.
    """
    try:
        tags = set(Locale.parse(locale).plural_form.tags)
    except (UnknownLocaleError, ValueError):
        return {"other"}

    return tags | {"other"}
