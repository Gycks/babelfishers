# Configuration

A Babel Fishers project is described by one file named `babelfishers.toml`. It lives in the folder where you run the commands. The `init` command creates it for you.

The file has four sections.

| Section | Required | Purpose |
|---|---|---|
| [`[locale]`](#the-locale-section) | Yes | The source language and the languages to translate into. |
| [`[engine]`](#the-engine-section) | Yes | The default translation provider. |
| [`[resources]`](#the-resources-section) | No | The files to translate. Nothing is translated without it. |
| [`[translation]`](#the-translation-section) | No | Extra translation settings such as a glossary. |

## A minimal file

```toml
[locale]
source = "en"
targets = ["fr", "de"]

[engine]
provider = "deepl"

[resources.json]
paths = ["locales/[source]/*.json"]
```

## The locale section

```toml
[locale]
source = "en"
targets = ["fr", "de", "ja"]
```

- `source` is the language of your original files.
- `targets` is the list of languages to translate into.

Use plain language codes, for example `pt` and not `pt-BR`. Regional variants are not supported. Run `babelfishers locales` to list every code you can use.

If the source language also appears in `targets`, it is ignored. Repeated codes are counted once.

## The engine section

```toml
[engine]
provider = "deepl"
```

`provider` is the translation provider that handles your text. The name is not case sensitive. See [Translation providers](providers.md) for the values you can use and the credentials each one needs.

## The resources section

This section lists the files to translate. Add one table for each format you use. The name after `resources.` is the [config key of the format](../formats.md), such as `json`, `po` or `android`.

Each table has one key, `paths`. It holds a list of files.

```toml
[resources.json]
paths = ["locales/[source]/*.json"]

[resources.po]
paths = ["i18n/[source]/*.po"]
```

### Path patterns

A path can use wildcards.

- `*` matches any part of a name inside one folder.
- `**` matches any number of folders.
- `?` matches one character.

Paths are relative to the folder where you run the command.

### The `[source]` placeholder

Write `[source]` where the language code appears in your paths. Babel Fishers reads your files with `[source]` set to the source language. It writes each translation with `[source]` set to the target language.

| Path in the config | File it reads | File it writes for `fr` |
|---|---|---|
| `locales/[source]/app.json` | `locales/en/app.json` | `locales/fr/app.json` |
| `messages_[source].properties` | `messages_en.properties` | `messages_fr.properties` |
| `strings/app.json` | `strings/app.json` | `strings/app_fr.json` |

The last row has no `[source]`. In that case the translation is written next to the original with the language code added to the name.

### Options for a path

A path can be a plain string. It can also be a table with more options.

```toml
[resources.json]
paths = [
  "locales/[source]/common.json",
  { path = "locales/[source]/pages/**/*.json", exclude = ["locales/[source]/pages/draft/**"], engine = "anthropic", excluded_keys = ["app.name"] },
]
```

| Key | Required | What it does |
|---|---|---|
| `path` | Yes | The file or pattern to translate. |
| `exclude` | No | A list of files or patterns to skip. |
| `engine` | No | A provider to use for these files instead of the default. |
| `excluded_keys` | No | Keys inside the files that must stay untranslated. |

The way to write a key depends on the format. See [Leave content out](../formats.md#leave-content-out).

A table can also be written on separate lines. Use this form when the options make the line too long.

```toml
[[resources.json.paths]]
path = "locales/[source]/pages/**/*.json"
exclude = ["locales/[source]/pages/draft/**"]
engine = "anthropic"
excluded_keys = ["app.name"]
```

!!! warning "Keep an inline table on one line"

    A table written with braces must fit on a single line. A line break inside the braces is an error. Use the `[[...]]` form above instead.

### Several formats in one project

```toml
[resources.json]
paths = ["web/locales/[source]/*.json"]

[resources.android]
paths = [
  { path = "app/src/main/res/values-[source]/strings.xml", excluded_keys = ["debug_only_string"] },
]

[resources.apple]
paths = ["ios/[source].lproj/Localizable.strings"]

[resources.po]
paths = ["locale/[source]/LC_MESSAGES/messages.po"]
```

## The translation section

This section is optional. It holds settings that shape the translation.

```toml
[translation]
glossary = "glossary.json"
```

`glossary` is the path to a JSON file. See [Glossaries](glossaries.md) for its structure.

## A complete example

```toml
[locale]
source = "en"
targets = ["fr", "de", "ja", "es"]

[engine]
provider = "deepl"

[translation]
glossary = "glossary.json"

[resources.json]
paths = [
  "locales/[source]/common.json",
  { path = "locales/[source]/pages/**/*.json", engine = "anthropic", excluded_keys = ["app.name"] },
]

[resources.po]
paths = ["locale/[source]/LC_MESSAGES/messages.po"]
```

## If the file is not valid

Every command that reads the file checks it first. Babel Fishers stops and names the problem. These are the common ones.

| Message | What to do |
|---|---|
| No Babel Fishers project found | Run `babelfishers init` in this folder, or move to the folder that has the file. |
| Could not find a valid section named locale | Add a `[locale]` section. The same goes for `engine`. |
| Source locale is not supported | Use a code from `babelfishers locales`. |
| The Engine is not supported | Use one of the values on the [providers page](providers.md). |
| Invalid resource type | Check the name after `resources.` against the [formats](../formats.md) table. |

For more help, see [Troubleshooting](troubleshooting.md).
