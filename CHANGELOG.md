# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- JSON and YAML: a key that contains a dot, such as `"home.title"` in a flat file, no longer stops the run. YAML keys read as booleans, such as `yes:` and `no:`, are translated in place instead of being added again as `'True':` and `'False':`.
- Android strings and XLIFF: text with an escaped character, such as `Terms &amp; Conditions`, is written correctly. It used to fail after the provider had translated it, so the file was not written and the text was paid for again on the next run.
- Android strings, XLIFF and .NET resx: comments before or after the root element, such as a license header, are kept.

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
