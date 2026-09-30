from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from babelfishers.models.culture import Culture
from babelfishers.models.engine import Engine


SUPPORTED_CULTURES: dict[str, Culture] = {
    lang.code: lang
    for lang in [
        # Plain codes that stand for one regional variant, the same on every engine.
        Culture(code="de", name="German", default_variant="de-DE"),
        Culture(code="en", name="English", default_variant="en-US"),
        Culture(code="es", name="Spanish", default_variant="es-ES"),
        Culture(code="fr", name="French", default_variant="fr-FR"),
        Culture(code="no", name="Norwegian", default_variant="nb"),
        Culture(code="pt", name="Portuguese", default_variant="pt-PT"),
        Culture(code="zh", name="Chinese", default_variant="zh-Hans"),
        # Regional variants.
        Culture(code="de-CH", name="German (Switzerland)"),
        Culture(code="de-DE", name="German (Germany)"),
        Culture(code="en-GB", name="English (UK)"),
        Culture(code="en-US", name="English (US)"),
        Culture(code="es-419", name="Spanish (Latin America)"),
        Culture(code="es-ES", name="Spanish (Spain)"),
        Culture(code="es-MX", name="Spanish (Mexico)"),
        Culture(code="fr-CA", name="French (Canada)"),
        Culture(code="fr-FR", name="French (France)"),
        Culture(code="pt-BR", name="Portuguese (Brazil)"),
        Culture(code="pt-PT", name="Portuguese (Portugal)"),
        Culture(code="sr-Cyrl", name="Serbian (Cyrillic)"),
        Culture(code="sr-Latn", name="Serbian (Latin)"),
        Culture(code="zh-Hans", name="Chinese (Simplified)"),
        Culture(code="zh-Hant", name="Chinese (Traditional)"),
        # Languages.
        Culture(code="af", name="Afrikaans"),
        Culture(code="am", name="Amharic"),
        Culture(code="ar", name="Arabic"),
        Culture(code="as", name="Assamese"),
        Culture(code="ay", name="Aymara"),
        Culture(code="az", name="Azerbaijani"),
        Culture(code="ba", name="Bashkir"),
        Culture(code="be", name="Belarusian"),
        Culture(code="bg", name="Bulgarian"),
        Culture(code="bho", name="Bhojpuri"),
        Culture(code="bn", name="Bengali"),
        Culture(code="br", name="Breton"),
        Culture(code="bs", name="Bosnian"),
        Culture(code="ca", name="Catalan"),
        Culture(code="ceb", name="Cebuano"),
        Culture(code="ckb", name="Kurdish (Sorani)"),
        Culture(code="cs", name="Czech"),
        Culture(code="cy", name="Welsh"),
        Culture(code="da", name="Danish"),
        Culture(code="dv", name="Divehi"),
        Culture(code="el", name="Greek"),
        Culture(code="et", name="Estonian"),
        Culture(code="eu", name="Basque"),
        Culture(code="fa", name="Persian"),
        Culture(code="fi", name="Finnish"),
        Culture(code="fil", name="Filipino"),
        Culture(code="ga", name="Irish"),
        Culture(code="gl", name="Galician"),
        Culture(code="gn", name="Guarani"),
        Culture(code="gom", name="Konkani"),
        Culture(code="gu", name="Gujarati"),
        Culture(code="ha", name="Hausa"),
        Culture(code="he", name="Hebrew"),
        Culture(code="hi", name="Hindi"),
        Culture(code="hr", name="Croatian"),
        Culture(code="ht", name="Haitian Creole"),
        Culture(code="hu", name="Hungarian"),
        Culture(code="hy", name="Armenian"),
        Culture(code="id", name="Indonesian"),
        Culture(code="ig", name="Igbo"),
        Culture(code="is", name="Icelandic"),
        Culture(code="it", name="Italian"),
        Culture(code="ja", name="Japanese"),
        Culture(code="jv", name="Javanese"),
        Culture(code="ka", name="Georgian"),
        Culture(code="kk", name="Kazakh"),
        Culture(code="km", name="Khmer"),
        Culture(code="kmr", name="Kurdish (Kurmanji)"),
        Culture(code="kn", name="Kannada"),
        Culture(code="ko", name="Korean"),
        Culture(code="ky", name="Kyrgyz"),
        Culture(code="lb", name="Luxembourgish"),
        Culture(code="ln", name="Lingala"),
        Culture(code="lo", name="Lao"),
        Culture(code="lt", name="Lithuanian"),
        Culture(code="lv", name="Latvian"),
        Culture(code="mai", name="Maithili"),
        Culture(code="mg", name="Malagasy"),
        Culture(code="mi", name="Māori"),
        Culture(code="mk", name="Macedonian"),
        Culture(code="ml", name="Malayalam"),
        Culture(code="mn", name="Mongolian (Cyrillic)"),
        Culture(code="mr", name="Marathi"),
        Culture(code="ms", name="Malay"),
        Culture(code="mt", name="Maltese"),
        Culture(code="my", name="Burmese"),
        Culture(code="nb", name="Norwegian (Bokmål)"),
        Culture(code="ne", name="Nepali"),
        Culture(code="nl", name="Dutch"),
        Culture(code="oc", name="Occitan"),
        Culture(code="om", name="Oromo"),
        Culture(code="or", name="Odia"),
        Culture(code="pa", name="Punjabi (Gurmukhi)"),
        Culture(code="pl", name="Polish"),
        Culture(code="prs", name="Dari"),
        Culture(code="ps", name="Pashto"),
        Culture(code="qu", name="Quechua"),
        Culture(code="ro", name="Romanian"),
        Culture(code="ru", name="Russian"),
        Culture(code="rw", name="Kinyarwanda"),
        Culture(code="sd", name="Sindhi"),
        Culture(code="si", name="Sinhala"),
        Culture(code="sk", name="Slovak"),
        Culture(code="sl", name="Slovenian"),
        Culture(code="so", name="Somali"),
        Culture(code="sq", name="Albanian"),
        Culture(code="st", name="Sesotho"),
        Culture(code="su", name="Sundanese"),
        Culture(code="sv", name="Swedish"),
        Culture(code="sw", name="Swahili"),
        Culture(code="ta", name="Tamil"),
        Culture(code="te", name="Telugu"),
        Culture(code="tg", name="Tajik"),
        Culture(code="th", name="Thai"),
        Culture(code="ti", name="Tigrinya"),
        Culture(code="tk", name="Turkmen"),
        Culture(code="tn", name="Setswana"),
        Culture(code="tr", name="Turkish"),
        Culture(code="ts", name="Tsonga"),
        Culture(code="tt", name="Tatar"),
        Culture(code="ug", name="Uyghur"),
        Culture(code="uk", name="Ukrainian"),
        Culture(code="ur", name="Urdu"),
        Culture(code="uz", name="Uzbek (Latin)"),
        Culture(code="vi", name="Vietnamese"),
        Culture(code="wo", name="Wolof"),
        Culture(code="xh", name="Xhosa"),
        Culture(code="yi", name="Yiddish"),
        Culture(code="yo", name="Yoruba"),
        Culture(code="yue", name="Cantonese"),
        Culture(code="zu", name="Zulu"),
    ]
}

_BY_LOWERCASE_CODE: dict[str, str] = {code.lower(): code for code in SUPPORTED_CULTURES}

# Every machine translation engine translates these.
_EVERY_ENGINE = (
    "ar az bg bn ca cs da de-DE el en-US es-ES et eu fa fi fil fr-FR ga gl he hi hu id it ja ko ky lt lv ms "
    "nb nl pl pt-BR pt-PT ro ru sk sl sq sv th tr uk ur vi zh-Hans zh-Hant"
).split()
# DeepL, Azure and Google Cloud, but not LibreTranslate.
_DEEPL_AZURE_GOOGLE = (
    "af as ba be bho bs ckb cy gom gu ha hr ht hy ig is ka kk kmr lb ln mai mg mi mk ml mn mr mt my ne pa prs "
    "ps st sw ta te tk tn tt uz xh yue zu"
).split()
# Azure and Google Cloud, but not DeepL.
_AZURE_GOOGLE = "am dv km kn lo or rw sd si so ti ug yo".split()
# DeepL and Google Cloud, but not Azure.
_DEEPL_GOOGLE = "ay br ceb gn jv oc om qu su tg ts wo yi".split()


@dataclass(frozen=True)
class _EngineCodes:
    """
    The locales an engine translates, as the codes it expects on the wire.

    A locale missing from `targets` or `sources` is one the engine cannot translate into or from.
    """

    targets: Mapping[str, str]
    sources: Mapping[str, str]


def _engine_codes(
    codes: Iterable[str],
    overrides: Mapping[str, str] | None = None,
    wire: Callable[[str], str] = str,
    source: Callable[[str], str] = str,
) -> _EngineCodes:
    targets = {code: (overrides or {}).get(code, wire(code)) for code in codes}
    return _EngineCodes(targets=targets, sources={code: source(target) for code, target in targets.items()})


_LLM_CODES = _engine_codes(code for code, culture in SUPPORTED_CULTURES.items() if culture.default_variant is None)

_ENGINE_CODES: dict[Engine, _EngineCodes] = {
    # DeepL takes a regional variant only as a target, so the source is sent as its base language.
    Engine.DeepL: _engine_codes(
        [*_EVERY_ENGINE, *_DEEPL_AZURE_GOOGLE, *_DEEPL_GOOGLE, "de-CH", "en-GB", "es-419", "es-MX", "fr-CA"],
        overrides={"fil": "TL", "es-MX": "ES-419"},
        wire=str.upper,
        source=lambda target: target.split("-")[0],
    ),
    Engine.Azure: _engine_codes(
        [*_EVERY_ENGINE, *_DEEPL_AZURE_GOOGLE, *_AZURE_GOOGLE, "es-MX", "fr-CA", "sr-Cyrl", "sr-Latn"],
        overrides={
            "ckb": "ku",
            "de-DE": "de",
            "en-US": "en",
            "es-ES": "es",
            "fr-FR": "fr",
            "mn": "mn-Cyrl",
            "pt-BR": "pt",
        },
    ),
    Engine.GoogleTranslate: _engine_codes(
        [
            *_EVERY_ENGINE,
            *(code for code in _DEEPL_AZURE_GOOGLE if code != "prs"),
            *_AZURE_GOOGLE,
            *(code for code in _DEEPL_GOOGLE if code != "wo"),
            "fr-CA",
            "sr-Cyrl",
        ],
        overrides={
            "de-DE": "de",
            "en-US": "en",
            "es-ES": "es",
            "kmr": "ku",
            "nb": "no",
            "sr-Cyrl": "sr",
            "zh-Hans": "zh-CN",
            "zh-Hant": "zh-TW",
        },
    ),
    Engine.LibreTranslate: _engine_codes(
        [*_EVERY_ENGINE, "sw"],
        overrides={"de-DE": "de", "en-US": "en", "es-ES": "es", "fil": "tl", "fr-FR": "fr", "pt-PT": "pt"},
    ),
    Engine.Anthropic: _LLM_CODES,
    Engine.OpenAI: _LLM_CODES,
    Engine.Mistral: _LLM_CODES,
    Engine.Google: _LLM_CODES,
    Engine.DeepSeek: _LLM_CODES,
}


def resolve_culture_code(culture_code: str) -> str | None:
    """Return the supported code as it is spelled in the catalog, whatever the case it was written in.

    Returns:
        The code, for example `pt-BR` for `pt-br`, or None when the locale is not supported.
    """
    return _BY_LOWERCASE_CODE.get(culture_code.lower())


def _get_culture(culture_code: str) -> Culture:
    culture = SUPPORTED_CULTURES.get(culture_code)
    if culture is None:
        raise ValueError(f"Culture code {culture_code} is not supported.")

    return culture


def get_culture_variant(culture_code: str) -> str:
    """Return the locale a code translates as: the default variant of a plain code such as `pt`, else the code."""
    return _get_culture(culture_code).default_variant or culture_code


def get_distinct_targets(source: str, targets: Iterable[str]) -> list[str]:
    """Drop repeated targets and targets that are the source locale, comparing the locales they translate as.

    Raises:
        ValueError: When two targets are the same locale under different codes, such as `pt` and `pt-PT`.
    """
    source_variant = get_culture_variant(source)
    by_variant: dict[str, str] = {}
    for code in dict.fromkeys(targets):
        variant = get_culture_variant(code)
        if variant == source_variant:
            continue

        if variant in by_variant:
            raise ValueError(
                f"Target locales {by_variant[variant]} and {code} are both {get_culture_name(code)}. Keep one."
            )
        by_variant[variant] = code

    return list(by_variant.values())


def is_supported_by(culture_code: str, engine: Engine, as_source: bool = False) -> bool:
    codes = _ENGINE_CODES[engine]
    return get_culture_variant(culture_code) in (codes.sources if as_source else codes.targets)


def get_unsupported_cultures(engine: Engine, source: str, targets: Iterable[str]) -> list[str]:
    """Return the codes `engine` can't translate: the source first if it can't translate from it, then the targets."""
    unsupported = [target for target in targets if not is_supported_by(target, engine)]
    if not is_supported_by(source, engine, as_source=True):
        unsupported.insert(0, source)

    return unsupported


def get_culture_code_for_engine(culture_code: str, engine: Engine, as_source: bool = False) -> str:
    codes = _ENGINE_CODES[engine]
    variant = get_culture_variant(culture_code)
    code = (codes.sources if as_source else codes.targets).get(variant)
    if code is None:
        raise ValueError(f"The engine {engine.value} does not support the locale {culture_code}.")

    return code


def get_culture_name(culture_code: str) -> str:
    return _get_culture(get_culture_variant(culture_code)).name
