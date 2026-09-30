# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Apple String Catalogs (`.xcstrings`). Translations are marked Needs Review for Xcode. A translation waiting for review or already approved is left alone while its source text stays the same, and is translated again when the source text changes. The run lock remembers which source text each translation came from.
- CSV and TSV files. A file with a column per locale gets its empty target cells filled in place, and a cell is translated again when its source text changes. A file with a `value` column is written once per locale. The layout, the delimiter and the columns are detected from the header, and a column for a locale that isn't supported stops the run when the configuration loads. `delimiter` and `columns` on a path entry override detection.

### Changed
- `ci` holds back a file that several locales write to, such as a String Catalog, when a provider failed on any of those locales. None of its locales are recorded as up to date, so the next run finishes it and the file is published whole.

## [0.1.2] - 2026-09-29

### Fixed
- JSON and YAML: a key that contains a dot, such as `"home.title"` in a flat file, no longer stops the run. YAML keys read as booleans, such as `yes:` and `no:`, are translated in place instead of being added again as `'True':` and `'False':`.
- Android strings and XLIFF: text with an escaped character, such as `Terms &amp; Conditions`, is written correctly. It used to fail after the provider had translated it, so the file was not written and the text was paid for again on the next run.
- Android strings, XLIFF and .NET resx: comments before or after the root element, such as a license header, are kept.
- Android strings and XLIFF: XML entities such as `&amp;` and `&lt;` are protected like placeholders, so the provider can't turn them into a bare `&` or `<`. Such a translation used to fail the whole file, and every string in it was paid for again on the next run.
- A key that appears more than once in a file, such as a repeated Java properties or Apple strings key, or a flat `"home.title"` next to a nested `home` with a `title` in JSON, YAML or ARB, no longer mixes up translations. Every value with that key is translated in its own place and a warning is printed. Before, a translation could be written into the wrong value, or given the placeholders of another entry with the same key. An `excluded_keys` entry for such a key is ignored, with a warning, since it can't tell the values apart.

### Changed
- `ci` publishes only the files that were translated completely. A file a provider failed on is left out of the pull request, and the job then fails with an error that names it. The translation memory still keeps what was translated for it. If the provider failed on every file, nothing is published.
- When a provider fails on one file, the other files are still translated, and `translate` and `ci` end with an error that names the files it failed on. Before, the run stopped, and in CI the other files' translations were not published.

## [0.1.1] - 2026-09-24

### Fixed
- LibreTranslate: placeholders are now masked with plain numbers, which LibreTranslate copies through. The previous text markers could come back altered or dropped, leaving stray characters such as `{amount}z`.
- A translation whose placeholders still differ from the source after every retry and provider is no longer written or saved in the translation memory. It keeps its source value and is tried again on the next run. The check now also counts repeated placeholders, so `%s and %s` translated with a single `%s` is caught.
- Translations in the memory whose placeholders differ from the source are translated again.
- gettext: translated `.po` files now carry the target locale in the `Language` header and the target's `Plural-Forms`, instead of copying the source header. Plural entries get the number of `msgstr[n]` forms the target needs, for example 3 for Polish and Russian, 6 for Arabic and 1 for Japanese, so gettext picks the right form at runtime.

### Changed
- When the last provider fails partway through a file, the text already translated is kept instead of the whole file failing. A file with untranslated text is not recorded as up to date, so the next run translates only what is missing.

## [0.1.0] - 2026-09-23

### Added
- Initial release.
- Ten file formats: JSON, HTML, YAML, Java properties, Android strings, gettext, Apple strings, Flutter ARB, XLIFF, .NET resx.
- Nine translation providers, selectable per project or per file group.
- Placeholder protection, glossaries, and a local translation memory.
- `babelfishers ci`: run translations in CI and publish them as a pull request, for GitHub Actions and GitLab CI/CD.
