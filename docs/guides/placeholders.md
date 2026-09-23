# Placeholders and protected content

A placeholder is a part of a text that your app fills in while it runs. `{name}` and `%d` are placeholders. A translation provider does not know that. It may translate the word inside the braces, move it or delete it. Then your app shows broken text or fails.

Babel Fishers protects placeholders so that this does not happen.

## How protection works

1. **Find.** Each text is scanned for placeholders.
2. **Hide.** Every placeholder is replaced by a marker that the provider is told to leave alone.
3. **Translate.** The provider translates the words around the markers.
4. **Restore.** The markers are replaced by the original placeholders.
5. **Check.** Babel Fishers verifies that every placeholder came back.

Each provider gets the kind of marker it handles best. You do not need to configure anything.

## What is protected

| Style | Examples | Where |
|---|---|---|
| Curly braces | `{name}`, `{0}`, ICU messages such as `{count, plural, one{1 item} other{# items}}` | Every format |
| printf | `%s`, `%d`, `%1$s`, `%.2f`, `%ld`, `%@` | JSON, Java properties, Android, gettext, Apple strings, XLIFF |
| Rails | `%{name}` | YAML |
| Symfony | `%name%` | YAML |
| Python | `%(name)s` | gettext |
| Apple | `%arg`, `%#@count@` | Apple strings |
| Inline tags | `<xliff:g id="n">%d</xliff:g>`, `<g>`, `<x/>` | Android, XLIFF |
| Glossary terms | Terms marked as not translatable | Every format |

The [format pages](../formats.md) list what each format protects. Glossary terms are covered in [Glossaries](glossaries.md).

### Quotes in ICU messages

In ICU messages an apostrophe followed by a brace, as in `'{'`, means a literal brace. Babel Fishers follows that rule. An ordinary apostrophe, as in `don't`, is left as plain text.

## If a placeholder does not come back

After translation, Babel Fishers checks that the protected markers are intact. If one is damaged or missing, that attempt counts as failed. It is tried again, and then the next provider is used if you set one. See [Translation providers](providers.md).

A second check compares the placeholders in the source with those in the translation. When they differ, you see a warning like this one.

```text
Placeholder mismatch for unit 'greeting': expected ['{name}'], got ['{nom}']
```

The file is still written. Open it and fix the text, or translate again with another provider. See [Troubleshooting](troubleshooting.md).

## Plural forms

Android strings and Flutter ARB files can hold plural forms. Each form is translated on its own. Babel Fishers does not add forms that your source file does not have.

Languages use different forms. English has `one` and `other`. Russian has `one`, `few`, `many` and `other`. Japanese has only `other`.

Babel Fishers compares the forms in your source file with the forms that the target language lists. If the target language lists a form that your file lacks, it logs a warning like this one.

```text
[fr] Plural group 'apples' (android) is missing required CLDR categories: ['many']
```

This is a warning and not an error. The file is still written.

The warning is not always a real problem. Some languages list a form that ordinary counts rarely use. French and Spanish list `many`, which applies only to very large numbers such as one million. For those languages you can often ignore the warning.

In other cases the missing form matters. Russian needs `few` and `many` to get the grammar right for many counts. Then add the missing forms to your source file. You can copy the text of `other`. Each form is then translated.

## Keep other content untouched

Some content is not a placeholder but must stay as it is. You have three options.

- **Keys.** List them in `excluded_keys`. See [Leave content out](../formats.md#leave-content-out).
- **HTML.** Add `translate="no"` or `class="notranslate"` to the element.
- **Terms.** Add them to a glossary as terms that are not translatable. See [Glossaries](glossaries.md).
