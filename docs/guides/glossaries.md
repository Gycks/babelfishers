# Glossaries

A glossary is a JSON file that tells Babel Fishers how to treat specific words and phrases. You can use it to do three things.

- Keep a term exactly as written, such as a product name.
- Force a fixed translation of a term in each language.
- Give the provider extra context, so an ambiguous word is translated correctly.

## Turn it on

Point the `[translation]` section of `babelfishers.toml` at your glossary file.

```toml
[translation]
glossary = "glossary.json"
```

The path is relative to the folder where you run the commands. The file must end in `.json`. If the file does not exist, Babel Fishers stops with an error. If you leave the section out, no glossary is used.

## The file

The file holds a list of entries. Each entry describes one term.

```json
[
  {
    "term": "Babel Fishers",
    "translatable": false
  },
  {
    "term": "Dashboard",
    "translatable": false,
    "translations": { "fr": "Tableau de bord", "de": "Übersicht" }
  },
  {
    "term": "Bank",
    "translatable": true,
    "context": "A financial institution, not the side of a river."
  }
]
```

| Field | Required | What it does |
|---|---|---|
| `term` | Yes | The word or phrase to look for. |
| `translatable` | Yes | `false` means the provider must not translate the term. `true` means it is translated as usual. |
| `translations` | No | The fixed translation for each language, by language code. Used when `translatable` is `false`. |
| `context` | No | A note for the provider. Used when `translatable` is `true`. |

!!! warning "Always set `translatable`"

    If you leave `translatable` out, the term is treated as `false`. It will not be translated.

## Keep a term as it is

Set `translatable` to `false` and give no translations. The term is copied unchanged into every language.

```json
{ "term": "Babel Fishers", "translatable": false }
```

## Fix the translation of a term

Set `translatable` to `false` and list the translation for each language.

```json
{
  "term": "Dashboard",
  "translatable": false,
  "translations": { "fr": "Tableau de bord", "es": "Panel" }
}
```

Every language you list gets that exact text. A language you do not list gets the term unchanged.

## Give the provider context

Set `translatable` to `true` and describe how the term is used.

```json
{
  "term": "Bank",
  "translatable": true,
  "context": "A financial institution, not the side of a river."
}
```

The term is still translated by the provider. The context is sent along with it, so the provider can choose the right meaning. This works with DeepL and the AI models. Azure, Google Cloud Translation and LibreTranslate ignore context. See [Translation providers](providers.md).

### Context for a whole string

A `term` can be the entire text of a value in your files. Then the entry applies to that value alone, and its context is sent with it.

```json
{
  "term": "Post",
  "translatable": true,
  "context": "A button label. It publishes a blog article."
}
```

This is useful for short strings that are hard to understand alone. You can add an entry for each of them, only to pass the context. Their translations are still done by the provider.

For a whole-string match, the glossary context replaces any context that came from the file, such as a gettext comment.

## How terms are found

- Matching ignores upper and lower case.
- A term matches only as a whole word. `cat` is not found inside `concatenate`.
- When two terms overlap, the longer one wins.
- When the entire value equals a term that is not translatable, the provider is not called at all. You are not charged for it.
- When a term is replaced, it is written the way the glossary spells it.

## After you change a glossary

Babel Fishers notices that the glossary changed and marks the files as needing another run. Text that was translated before is stored in the [translation memory](translation-memory.md) and is reused as it was.

To apply a new glossary to text that is already stored, clear the memory first.

```bash
babelfishers memory clear
babelfishers translate
```

## Entries that are skipped

An entry is skipped with a warning when any of these is true.

- `term` is missing, empty or not a string.
- `translatable` is not a true or false value.
- `translations` uses a language code that is not supported.

The rest of the file is still used.
