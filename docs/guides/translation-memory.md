# Translation memory

The translation memory is a local store of translations that Babel Fishers has already made. Before it asks your provider, it looks in the memory. Text that is found there is reused. Only new text goes to the provider.

This means you pay for the same text once.

## How it works

- After a file is translated, the new translations are saved in the memory.
- An entry is identified by the source text, the source language and the target language. Spaces at the start and end of the text are ignored.
- The file and the key do not matter. If `Save` appears in ten files, it is translated once.
- Each entry also records which provider made it and when it was last used.
- The original text is not stored. Only a fingerprint of it is kept, next to the translation.

The memory is one file, `.babelfishers/store.sqlite`, in your project folder. It is created on the first run.

## See what it holds

```bash
babelfishers memory stats
```

This shows how many entries there are, the size of the file, the date of the oldest entry and the last use. It also lists the entries for each provider.

Before you translate, `babelfishers translate --dry-run` shows how many texts would come from the memory.

## Remove entries

Use `prune` to remove some entries. Pass exactly one filter.

```bash
babelfishers memory prune --older-than 90
babelfishers memory prune --engine deepl
babelfishers memory prune --keep 5000
```

| Option | What it removes |
|---|---|
| `--older-than DAYS` | Entries that were not used in the last number of days. |
| `--engine NAME` | Entries made by that provider. |
| `--keep COUNT` | Everything except the most recently used entries. |

Use `clear` to remove everything. It asks for confirmation first. Add `--yes` to skip the question.

```bash
babelfishers memory clear
```

## When to clear or prune

The memory reuses a translation whatever provider made it and whatever context was sent. It does not check whether the result is still what you want. Remove entries when you want fresh translations.

- **You changed your glossary.** Old translations do not use the new terms. See [Glossaries](glossaries.md).
- **You switched provider.** Run `memory prune --engine` with the old provider to translate its text again.
- **A translation is poor.** Clear the memory, or prune it, and run again.

## The run record

A second file sits beside the memory. It is `.babelfishers/run.lock`. The memory holds text. The run record holds which files were translated.

For each source file and language, it stores a fingerprint of the source and of your settings. On the next run, a file is translated again only when it is stale. There are four reasons.

| Status | Meaning |
|---|---|
| `new` | This file and language were never translated. |
| `target missing` | The translated file does not exist. |
| `source changed` | The source file changed since the last run. |
| `config changed` | Your provider or your glossary changed. |

A file that is none of these is skipped. The dry run shows the status of every file and language.

Two commands manage the record.

```bash
babelfishers run_lock prune
babelfishers run_lock refresh
```

- `run_lock prune` deletes the record. Every file counts as new on the next run. The memory still supplies text it already has.
- `run_lock refresh` rebuilds the record from your files. It marks every translated file that exists as up to date and translates nothing. It assumes your existing translations match your current sources.

If you clone a project without the `.babelfishers` folder, run `run_lock refresh` before you translate. Otherwise everything is translated again.

## Share it with your team

Commit the `.babelfishers` folder with your project. Your teammates and your CI then reuse the same memory and record. At the end of each run the memory file is complete on its own.

The memory is a binary file. If two branches both change it, Git cannot merge the two versions. Keep one of them. Any text that is missing from it is translated again when it is needed.
