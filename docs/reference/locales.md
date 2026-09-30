# Supported locales

Babel Fishers supports 133 locale codes. Use them in the `[locale]` section of `babelfishers.toml`.

To list them in your terminal, run `babelfishers locales`. To filter by code or name, use `--search`.

```bash
babelfishers locales --search fr
```

## Which provider supports which locale

AI providers (`openai`, `anthropic`, `google`, `mistral` and `deepseek`) translate every locale on this page.

Each translation service has its own list, shown in the tables below. When a locale in `[locale]` is missing from the list of the provider in `[engine]`, or of a provider set with `engine` on a path, the configuration fails to load and names the locales. Nothing is translated.

## Writing a locale code

Codes are not case sensitive. `pt-br`, `PT-BR` and `pt-BR` are the same locale.

Babel Fishers then uses the spelling shown on this page wherever the code appears: in the `[source]` part of a path, in the files it writes and in its reports. With `pt-br` in `targets`, `locales/[source]/app.json` becomes `locales/pt-BR/app.json`. Name your folders with that spelling.

## Plain codes

You don't need a regional code for these languages. Each plain code stands for one variant, and every provider translates into that same variant.

| Code | Translates as |
|---|---|
| `de` | German (Germany), `de-DE` |
| `en` | English (US), `en-US` |
| `es` | Spanish (Spain), `es-ES` |
| `fr` | French (France), `fr-FR` |
| `no` | Norwegian (Bokmål), `nb` |
| `pt` | Portuguese (Portugal), `pt-PT` |
| `zh` | Chinese (Simplified), `zh-Hans` |

A plain code and the variant it stands for are the same locale. You can't list both in `targets`, for example `pt` and `pt-PT`. When a target is the source locale under its other code, such as `en-US` with `source = "en"`, it is ignored.

## Languages

| Code | Language | DeepL | Azure | Google Cloud | LibreTranslate |
|---|---|:-:|:-:|:-:|:-:|
| `af` | Afrikaans | ✓ | ✓ | ✓ |  |
| `sq` | Albanian | ✓ | ✓ | ✓ | ✓ |
| `am` | Amharic |  | ✓ | ✓ |  |
| `ar` | Arabic | ✓ | ✓ | ✓ | ✓ |
| `hy` | Armenian | ✓ | ✓ | ✓ |  |
| `as` | Assamese | ✓ | ✓ | ✓ |  |
| `ay` | Aymara | ✓ |  | ✓ |  |
| `az` | Azerbaijani | ✓ | ✓ | ✓ | ✓ |
| `ba` | Bashkir | ✓ | ✓ | ✓ |  |
| `eu` | Basque | ✓ | ✓ | ✓ | ✓ |
| `be` | Belarusian | ✓ | ✓ | ✓ |  |
| `bn` | Bengali | ✓ | ✓ | ✓ | ✓ |
| `bho` | Bhojpuri | ✓ | ✓ | ✓ |  |
| `bs` | Bosnian | ✓ | ✓ | ✓ |  |
| `br` | Breton | ✓ |  | ✓ |  |
| `bg` | Bulgarian | ✓ | ✓ | ✓ | ✓ |
| `my` | Burmese | ✓ | ✓ | ✓ |  |
| `yue` | Cantonese | ✓ | ✓ | ✓ |  |
| `ca` | Catalan | ✓ | ✓ | ✓ | ✓ |
| `ceb` | Cebuano | ✓ |  | ✓ |  |
| `hr` | Croatian | ✓ | ✓ | ✓ |  |
| `cs` | Czech | ✓ | ✓ | ✓ | ✓ |
| `da` | Danish | ✓ | ✓ | ✓ | ✓ |
| `prs` | Dari | ✓ | ✓ |  |  |
| `dv` | Divehi |  | ✓ | ✓ |  |
| `nl` | Dutch | ✓ | ✓ | ✓ | ✓ |
| `et` | Estonian | ✓ | ✓ | ✓ | ✓ |
| `fil` | Filipino | ✓ | ✓ | ✓ | ✓ |
| `fi` | Finnish | ✓ | ✓ | ✓ | ✓ |
| `gl` | Galician | ✓ | ✓ | ✓ | ✓ |
| `ka` | Georgian | ✓ | ✓ | ✓ |  |
| `el` | Greek | ✓ | ✓ | ✓ | ✓ |
| `gn` | Guarani | ✓ |  | ✓ |  |
| `gu` | Gujarati | ✓ | ✓ | ✓ |  |
| `ht` | Haitian Creole | ✓ | ✓ | ✓ |  |
| `ha` | Hausa | ✓ | ✓ | ✓ |  |
| `he` | Hebrew | ✓ | ✓ | ✓ | ✓ |
| `hi` | Hindi | ✓ | ✓ | ✓ | ✓ |
| `hu` | Hungarian | ✓ | ✓ | ✓ | ✓ |
| `is` | Icelandic | ✓ | ✓ | ✓ |  |
| `ig` | Igbo | ✓ | ✓ | ✓ |  |
| `id` | Indonesian | ✓ | ✓ | ✓ | ✓ |
| `ga` | Irish | ✓ | ✓ | ✓ | ✓ |
| `it` | Italian | ✓ | ✓ | ✓ | ✓ |
| `ja` | Japanese | ✓ | ✓ | ✓ | ✓ |
| `jv` | Javanese | ✓ |  | ✓ |  |
| `kn` | Kannada |  | ✓ | ✓ |  |
| `kk` | Kazakh | ✓ | ✓ | ✓ |  |
| `km` | Khmer |  | ✓ | ✓ |  |
| `rw` | Kinyarwanda |  | ✓ | ✓ |  |
| `gom` | Konkani | ✓ | ✓ | ✓ |  |
| `ko` | Korean | ✓ | ✓ | ✓ | ✓ |
| `kmr` | Kurdish (Kurmanji) | ✓ | ✓ | ✓ |  |
| `ckb` | Kurdish (Sorani) | ✓ | ✓ | ✓ |  |
| `ky` | Kyrgyz | ✓ | ✓ | ✓ | ✓ |
| `lo` | Lao |  | ✓ | ✓ |  |
| `lv` | Latvian | ✓ | ✓ | ✓ | ✓ |
| `ln` | Lingala | ✓ | ✓ | ✓ |  |
| `lt` | Lithuanian | ✓ | ✓ | ✓ | ✓ |
| `lb` | Luxembourgish | ✓ | ✓ | ✓ |  |
| `mk` | Macedonian | ✓ | ✓ | ✓ |  |
| `mai` | Maithili | ✓ | ✓ | ✓ |  |
| `mg` | Malagasy | ✓ | ✓ | ✓ |  |
| `ms` | Malay | ✓ | ✓ | ✓ | ✓ |
| `ml` | Malayalam | ✓ | ✓ | ✓ |  |
| `mt` | Maltese | ✓ | ✓ | ✓ |  |
| `mr` | Marathi | ✓ | ✓ | ✓ |  |
| `mn` | Mongolian (Cyrillic) | ✓ | ✓ | ✓ |  |
| `mi` | Māori | ✓ | ✓ | ✓ |  |
| `ne` | Nepali | ✓ | ✓ | ✓ |  |
| `nb` | Norwegian (Bokmål) | ✓ | ✓ | ✓ | ✓ |
| `oc` | Occitan | ✓ |  | ✓ |  |
| `or` | Odia |  | ✓ | ✓ |  |
| `om` | Oromo | ✓ |  | ✓ |  |
| `ps` | Pashto | ✓ | ✓ | ✓ |  |
| `fa` | Persian | ✓ | ✓ | ✓ | ✓ |
| `pl` | Polish | ✓ | ✓ | ✓ | ✓ |
| `pa` | Punjabi (Gurmukhi) | ✓ | ✓ | ✓ |  |
| `qu` | Quechua | ✓ |  | ✓ |  |
| `ro` | Romanian | ✓ | ✓ | ✓ | ✓ |
| `ru` | Russian | ✓ | ✓ | ✓ | ✓ |
| `st` | Sesotho | ✓ | ✓ | ✓ |  |
| `tn` | Setswana | ✓ | ✓ | ✓ |  |
| `sd` | Sindhi |  | ✓ | ✓ |  |
| `si` | Sinhala |  | ✓ | ✓ |  |
| `sk` | Slovak | ✓ | ✓ | ✓ | ✓ |
| `sl` | Slovenian | ✓ | ✓ | ✓ | ✓ |
| `so` | Somali |  | ✓ | ✓ |  |
| `su` | Sundanese | ✓ |  | ✓ |  |
| `sw` | Swahili | ✓ | ✓ | ✓ | ✓ |
| `sv` | Swedish | ✓ | ✓ | ✓ | ✓ |
| `tg` | Tajik | ✓ |  | ✓ |  |
| `ta` | Tamil | ✓ | ✓ | ✓ |  |
| `tt` | Tatar | ✓ | ✓ | ✓ |  |
| `te` | Telugu | ✓ | ✓ | ✓ |  |
| `th` | Thai | ✓ | ✓ | ✓ | ✓ |
| `ti` | Tigrinya |  | ✓ | ✓ |  |
| `ts` | Tsonga | ✓ |  | ✓ |  |
| `tr` | Turkish | ✓ | ✓ | ✓ | ✓ |
| `tk` | Turkmen | ✓ | ✓ | ✓ |  |
| `uk` | Ukrainian | ✓ | ✓ | ✓ | ✓ |
| `ur` | Urdu | ✓ | ✓ | ✓ | ✓ |
| `ug` | Uyghur |  | ✓ | ✓ |  |
| `uz` | Uzbek (Latin) | ✓ | ✓ | ✓ |  |
| `vi` | Vietnamese | ✓ | ✓ | ✓ | ✓ |
| `cy` | Welsh | ✓ | ✓ | ✓ |  |
| `wo` | Wolof | ✓ |  |  |  |
| `xh` | Xhosa | ✓ | ✓ | ✓ |  |
| `yi` | Yiddish | ✓ |  | ✓ |  |
| `yo` | Yoruba |  | ✓ | ✓ |  |
| `zu` | Zulu | ✓ | ✓ | ✓ |  |

## Regional variants

| Code | Language | DeepL | Azure | Google Cloud | LibreTranslate |
|---|---|:-:|:-:|:-:|:-:|
| `zh-Hans` | Chinese (Simplified) | ✓ | ✓ | ✓ | ✓ |
| `zh-Hant` | Chinese (Traditional) | ✓ | ✓ | ✓ | ✓ |
| `en-GB` | English (UK) | ✓ |  |  |  |
| `en-US` | English (US) | ✓ | ✓ | ✓ | ✓ |
| `fr-CA` | French (Canada) | ✓ | ✓ | ✓ |  |
| `fr-FR` | French (France) | ✓ | ✓ | ✓ | ✓ |
| `de-DE` | German (Germany) | ✓ | ✓ | ✓ | ✓ |
| `de-CH` | German (Switzerland) | ✓ |  |  |  |
| `pt-BR` | Portuguese (Brazil) | ✓ | ✓ | ✓ | ✓ |
| `pt-PT` | Portuguese (Portugal) | ✓ | ✓ | ✓ | ✓ |
| `sr-Cyrl` | Serbian (Cyrillic) |  | ✓ | ✓ |  |
| `sr-Latn` | Serbian (Latin) |  | ✓ |  |  |
| `es-419` | Spanish (Latin America) | ✓ |  |  |  |
| `es-MX` | Spanish (Mexico) | ✓ | ✓ |  |  |
| `es-ES` | Spanish (Spain) | ✓ | ✓ | ✓ | ✓ |

- DeepL has no Mexican Spanish. It translates `es-MX` as Latin American Spanish.
- DeepL accepts a regional variant only as the language to translate into. When the source is a variant, such as `pt-BR`, DeepL receives the language alone.

## Plural rules

Babel Fishers checks plural forms and writes gettext `Plural-Forms` with the rules of each locale. Two locales need a note:

- Dari (`prs`) uses the rules of Persian as spoken in Afghanistan.
- Aymara (`ay`) has no published plural rules. Plural groups are only checked for the `other` form.
