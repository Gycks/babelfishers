# Troubleshooting

Most problems come with a message that names the cause. Find the message here, then follow the fix.

Two habits save time.

- Run `babelfishers translate --dry-run` first. It shows what would happen and calls no provider.
- Read the first error in the output. Later messages are often a result of it.

## Project and configuration

### No Babel Fishers project found

Babel Fishers looks for `babelfishers.toml` in the folder where you run the command. Move to your project folder, or run `babelfishers init` to create the file.

### Invalid configuration file

The message continues with the reason. This table lists them.

| Reason | Fix |
|---|---|
| Could not find a valid section named locale | Add a `[locale]` section. |
| Could not find a valid section named engine | Add an `[engine]` section. |
| Source locale not set | Add `source` to `[locale]`. |
| Target locales not set | Add `targets` to `[locale]`. |
| Source locale is not supported, or Target locales is malformed | Use codes from `babelfishers locales`. Use `pt` and not `pt-BR`. |
| Engine provider not set | Add `provider` to `[engine]`. |
| The Engine is not supported | Use a value from [Translation providers](providers.md). |

### The file must be a valid TOML file

The parser reports the line and the column of the error. Check quotes, brackets and commas. A table written with braces must fit on one line. See [Configuration](configuration.md#options-for-a-path).

### Invalid resource type or Resource is malformed

Check these points.

- The name after `resources.` must be a [format key](../formats.md), such as `json` or `po`.
- The table must hold only one key, `paths`.
- Each table in the list needs a `path`.
- `exclude` and `excluded_keys` must be lists.

## Files

### No resources found in the configuration

There is no `[resources.<format>]` table in the file. Add one. See [Configuration](configuration.md#the-resources-section).

### An entry will be skipped because it has no valid paths

The pattern did not match any file. Check that:

- You run the command from your project folder. Paths are relative to it.
- The pattern uses the right folders and `[source]`.

The dry run lists the files that were found. If it prints `No files to translate`, no file matched.

### Invalid file extension

A pattern matched a file of another type. For example `locales/**/*` in a `json` table also matches `.md` files. Narrow the pattern, for example `locales/**/*.json`.

### Up to date for every target locale, skipping

Nothing changed since the last run, so nothing is translated. To translate again, delete the translated file, or reset the record.

```bash
babelfishers run_lock prune
```

Text that is in the memory is reused. Clear the memory as well if you want new translations. See [Translation memory](translation-memory.md).

## Providers

### Environment variable is not set

The message names the missing variable, for example `BF_DEEPL_API_KEY`. Set it in the same terminal session where you run Babel Fishers. In CI, add it as a secret. AI providers also need a model ID. The [providers page](providers.md) lists every variable.

### Authorization failed

The provider rejected your key. Check that the key is correct and active. Check that it belongs to the provider you chose in `[engine]`.

### Quota exceeded or rate limited

You used up your plan, or you sent too much at once. Babel Fishers waits and tries again up to three times. If it still fails, wait for your limit to reset or raise your plan. Files that finished are recorded, so the next run continues where this one stopped.

### The provider refused, or returned no usable translation

An AI model refused the text, or its answer could not be read. Run again. If it repeats, use another model or provider for those files. See [Translation providers](providers.md).

### Unable to restore translation units

The provider damaged a protected term or placeholder. Babel Fishers tries again by itself. If it keeps failing, use another provider for those files.

### The translation pipeline failed

Every attempt failed, with every provider you set. The messages above this one give the cause. Fix it and run the command again.

## Results

### Placeholder mismatch

A placeholder in the translation differs from the source. Open the file and fix the text. See [Placeholders](placeholders.md).

### Plural group is missing required categories

The target language lists plural forms that your source file does not have. This is a warning, and the file is still written. It is not always a problem. For French the missing form is `many`, which only covers very large numbers, so you can often ignore it. For Russian, add the missing forms to your source file. See [Placeholders](placeholders.md#plural-forms).

### A glossary or provider change had no effect

Old translations come from the memory. Prune or clear it, then run again. See [Translation memory](translation-memory.md#when-to-clear-or-prune).

### Duplicate key warnings

A key appears twice in a file. The last one is kept. Remove the extra one to silence the warning.

### Glossary problems

- `Could not find glossary file` means the path in `[translation]` is wrong.
- `Glossary must be in a JSON format` means the file does not end in `.json`.
- `Skipping glossary entry` names an entry with a missing term, a bad `translatable` value or an unsupported language code. Fix the entry. See [Glossaries](glossaries.md).

## Still stuck?

Open an [issue on GitHub](https://github.com/Gycks/babelfishers/issues). Include the full message, the format of the file and your configuration with any secrets removed.
