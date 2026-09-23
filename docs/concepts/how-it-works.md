# How it works

This page explains what happens when you run `babelfishers translate`. You do not need it to use Babel Fishers. It helps you understand the cost and the result of a run.

## The big picture

```mermaid
flowchart LR
    A[Read the config] --> B[Find what changed]
    B --> C[Parse each source file]
    C --> D[Translate]
    D --> E[Write files and record the run]
```

1. **Read the config.** Babel Fishers loads `babelfishers.toml` and finds the files that your paths match.
2. **Find what changed.** It compares each file and language with the [run record](../guides/translation-memory.md#the-run-record). Files that are up to date are skipped.
3. **Parse each source file.** A file is read once, whatever its [format](../formats.md).
4. **Translate.** Each file is translated into each target language. Up to eight of these jobs run at the same time.
5. **Write and record.** The translated files are saved and the run is recorded.

## What happens to each text

Every text in a file goes through the same steps for each target language.

```mermaid
flowchart LR
    M[Check the memory] --> P[Protect] --> T[Translate] --> R[Restore] --> W[Write]
```

1. **Check the memory.** If the [translation memory](../guides/translation-memory.md) already has this text for this language pair, it is used. The provider is not called.
2. **Protect.** [Placeholders](../guides/placeholders.md) and glossary terms that must stay unchanged are replaced by markers.
3. **Translate.** The provider translates the words around the markers. Notes from your file and [glossary](../guides/glossaries.md) context are passed along to providers that use context.
4. **Restore.** The markers are replaced by the original text. Babel Fishers checks that every marker came back. It warns you when the placeholders in the translation differ from the source.
5. **Write.** The text is put back in its place in the file.

New translations are then stored in the memory, so the same text is never translated twice.

## What the provider receives

The provider receives the text of each value, with placeholders hidden, and any context notes. It does not receive your keys, your file names or the rest of your files.

## One parse, many languages

A source file is parsed once. Babel Fishers then makes a copy for each target language and fills each copy with its translations. So adding a language to `targets` does not repeat the parsing.

Only files that need work are parsed. A file that is up to date for every language is not read again.

## Saving is safe

Each translated file is first written to a temporary file next to its destination. Then it is moved into place. A crash in the middle of a write cannot leave a broken or half-written file.

## When something fails

- **Rate limits.** If the provider says you are sending too much, Babel Fishers waits and tries again, up to three times.
- **A failed attempt.** If a translation fails, Babel Fishers tries once more.
- **Fallback.** If you set a different provider for some files, the default provider is used when that one keeps failing. See [Translation providers](../guides/providers.md).
- **A final failure.** The run stops with an error. Files that already finished are recorded. The next run continues from there.

## Dry run

`babelfishers translate --dry-run` follows the same steps up to the point of calling the provider. It calls no provider and writes no file. It leaves the run record and the memory as they are.

It shows how many texts each file has, how many come from the memory and how many would be sent. The number of characters is an estimate. It assumes that no retry or fallback is needed.
