# Supported formats

Babel Fishers currently supports ten localization formats. Translated files are written back in the same format as the source.

| Format | Config key | File extensions |
|---|---|---|
| [JSON](#json) | `json` | `.json` |
| [HTML](#html) | `html` | `.html` |
| [YAML](#yaml) | `yaml` | `.yaml`, `.yml` |
| [Java properties](#java-properties) | `properties` | `.properties` |
| [Android strings](#android-strings) | `android` | `.xml` |
| [gettext](#gettext) | `po` | `.po` |
| [Apple strings](#apple-strings) | `apple` | `.strings` |
| [Flutter ARB](#flutter-arb) | `arb` | `.arb` |
| [XLIFF](#xliff) | `xliff` | `.xliff`, `.xlf` |
| [.NET resx](#net-resx) | `resx` | `.resx` |

The config key is the name you use in `babelfishers.toml`.

```toml
[resources.json]
paths = ["locales/[source]/*.json"]

[resources.po]
paths = ["i18n/[source]/*.po"]
```

## What all formats have in common

- Each source file is read once and written once per target locale.
- Only text values are translated. Keys and structure are kept.
- Empty values are skipped.
- Placeholders in curly braces, such as `{name}` or `{0}`, are protected in every format. Some formats protect more. Each section below lists them.
- If a key appears twice in a file, the last one is kept. Most formats also print a warning.

## JSON

**Config key:** `json`

- **Translated.** Every non-empty string value, at any depth and inside arrays.
- **Left alone.** Keys, numbers, booleans, `null` and empty strings.
- **Placeholders protected.** printf style such as `%s` and `%d`, and anything in braces.
- **Good to know.** Output uses two-space indentation. Non-ASCII characters are written as they are.

## HTML

**Config key:** `html`

- **Translated.** Visible text. Inline tags such as `<b>`, `<a>` and `<em>` stay inside the sentence they belong to. These attributes are translated too: `alt` on `img` and `area`, `placeholder` on `input` and `textarea`, and `title` on any element.
- **Left alone.** Everything in `<script>`, `<style>`, `<noscript>` and `<head>`. The page title and meta tags are inside `<head>`, so they are not translated.
- **Placeholders protected.** Anything in braces.
- **Good to know.** To skip part of a page, add `translate="no"` or `class="notranslate"` to the element. The [`excluded_keys`](#leave-content-out) option does not apply to HTML.

## YAML

**Config key:** `yaml`

- **Translated.** Every non-empty string value, at any depth and inside lists.
- **Left alone.** Keys and values that are not strings.
- **Placeholders protected.** Rails style `%{name}`, Symfony style `%name%`, and anything in braces.
- **Good to know.** Key order is kept. Comments are not kept in the translated files.

## Java properties

**Config key:** `properties`

- **Translated.** The value of each entry.
- **Left alone.** Keys, comments and blank lines.
- **Placeholders protected.** printf style, and anything in braces such as `{0}`.
- **Good to know.** Values that continue on the next line with a backslash are read as one value. Line endings are kept, whether LF or CRLF. Files are read and written as UTF-8. Entries are written as `key=value`.

## Android strings

**Config key:** `android`

- **Translated.** `<string>` elements, the items of `<string-array>`, and the items of `<plurals>`.
- **Left alone.** Anything marked `translatable="false"`.
- **Placeholders protected.** printf style, inline tags such as `<xliff:g>`, and anything in braces.
- **Good to know.** Text that mixes plain words with inline tags is translated as one piece.

## gettext

**Config key:** `po`

- **Translated.** The `msgid` text becomes the `msgstr` of the translated file. Plural entries are handled through `msgid_plural` and `msgstr[n]`. Entries with a `msgctxt` are supported.
- **Adapted to the target.** In the header entry, `Language` is set to the target locale and `Plural-Forms` to the target's gettext plural rule, the same one `pybabel init` writes. Each plural entry gets as many `msgstr[n]` forms as the target needs, for example 2 for `fr`, 3 for `pl` and `ru`, 6 for `ar` and 1 for `ja`. The form the target uses for a count of 1 is translated from `msgid`, and the other forms from `msgid_plural`. If the source has no header entry, one is added.
- **Left alone.** The other header fields and all comments.
- **Placeholders protected.** printf style, Python style such as `%(name)s`, and anything in braces.
- **Good to know.** Translator comments that start with `#.` are sent to the provider as context. The `fuzzy` flag is removed from entries once they are translated. Long lines are wrapped at 77 characters.

## Apple strings

**Config key:** `apple`

- **Translated.** The value of each key and value entry in a `.strings` file.
- **Left alone.** Keys and comments.
- **Placeholders protected.** printf style including `%@`, `%arg`, stringsdict references, and anything in braces.
- **Good to know.** The comment written above an entry is sent to the provider as context. Line endings are kept. Only `.strings` files are supported. `.stringsdict` and `.xcstrings` are not.

## Flutter ARB

**Config key:** `arb`

- **Translated.** Every non-empty string value. For ICU plural, select and selectordinal messages, each category is translated on its own.
- **Left alone.** Keys that start with `@`, such as `@greeting`. The selectors and structure of ICU messages.
- **Placeholders protected.** Anything in braces, including ICU arguments.
- **Good to know.** Output uses two-space indentation.

## XLIFF

**Config key:** `xliff`

- **Translated.** The `<source>` text of each unit. The result is written to `<target>`. A `<target>` is created if the unit has none.
- **Left alone.** Everything else in the document.
- **Placeholders protected.** Inline tags such as `<g>`, `<x/>` and `<ph>`, printf style, and anything in braces.
- **Good to know.** Version 1.2 and version 2 are both supported. Notes are sent to the provider as context. Files with several `<file>` elements are supported.

## .NET resx

**Config key:** `resx`

- **Translated.** The value of each `<data>` entry that holds text.
- **Left alone.** Entries with a `type` or `mimetype` attribute, such as embedded files and images.
- **Placeholders protected.** Anything in braces, such as `{0}`.
- **Good to know.** The `<comment>` of an entry is sent to the provider as context. CDATA sections stay CDATA sections.

## Leave content out

Use `excluded_keys` to keep specific entries untranslated. Use `exclude` to skip whole files. Both go on a path entry.

```toml
[resources.json]
paths = [
  { path = "locales/[source]/*.json", exclude = ["locales/[source]/legacy.json"], excluded_keys = ["app.name"] },
]
```

The way you write a key depends on the format.

| Format | Key to use |
|---|---|
| JSON, YAML, ARB | The path to the value, such as `app.name`. Use `items[0]` for list entries. |
| Java properties, Apple strings, resx | The key name. |
| Android | The name. Use `colors[0]` for array items and `apples.one` for plural items. |
| gettext | The `msgid` text. Use `msgid[0]`, `msgid[1]` and so on for plural forms, numbered as in the target's `Plural-Forms`. |
| XLIFF | The unit `id`. Use `file-id:unit-id` when a document has several files. |
| HTML | Not used. Mark elements in the source instead. |
