<img src="https://raw.githubusercontent.com/Gycks/babelfishers/main/docs/assets/banner.svg" alt="Babel Fishers. Localization on your terms." width="640">

[![PyPI](https://img.shields.io/pypi/v/babelfishers.svg)](https://pypi.org/project/babelfishers/)
[![Python versions](https://img.shields.io/pypi/pyversions/babelfishers.svg)](https://pypi.org/project/babelfishers/)
[![License](https://img.shields.io/pypi/l/babelfishers.svg)](LICENSE)

**Translate your app's localization files with your own provider key, without breaking them.**

Babel Fishers is a command-line tool. It sends only the translatable text to the provider you choose, keeps placeholders and plural forms intact, checks every string that comes back, and writes the file in its original format. In CI, it opens the pull request for you.

![Babel Fishers Demo](https://raw.githubusercontent.com/Gycks/babelfishers/main/docs/assets/demo.gif)

## Quickstart

```bash
pip install babelfishers    # Python 3.11+
babelfishers init           # writes babelfishers.toml
```

```toml
[locale]
source = "en"
targets = ["fr", "de"]

[engine]
provider = "deepl"

[resources.json]
paths = ["locales/[source]/*.json"]
```

See what would be translated. This needs no API key and writes nothing:

```text
$ babelfishers translate --dry-run

  File                 Locale  Status  Units  Cached  To translate  Chars  Engine
  locales/en/app.json  de      new         2       0             2     79  deepl
  locales/en/app.json  fr      new         2       0             2     79  deepl
```

Then set your provider's key as an environment variable and run it for real:

```bash
babelfishers translate
```

## How it works

A provider that sees `{name}` may hand back `{nom}`, and your app shows a raw token. Babel Fishers never gives it the chance:

```text
source    Hello, {name}! You have %d new messages.
written   Bonjour, {name} ! Vous avez %d nouveaux messages.
```

- **Nothing is written broken.** Every placeholder is checked after translation. A string that doesn't match is retried, then tried with a fallback provider if you set one. If it still doesn't match, it keeps the source text and you get a warning.
- **You never pay twice.** A translation memory kept in your repo means a string translated once is reused everywhere, CI included.
- **Pull requests from CI.** `babelfishers ci` translates what changed and opens or updates a pull request on GitHub Actions or GitLab CI/CD.
- **Your key, your provider.** DeepL, Azure, Google Cloud, LibreTranslate, or one of five AI models. With a self-hosted LibreTranslate server, your strings never leave your network.
- **Twelve formats, 133 locales.** From JSON and gettext to Android and String Catalogs, with regional variants such as `pt-BR`, `es-419` and `zh-Hant`.

See [How it works](https://gycks.github.io/babelfishers/concepts/how-it-works/) for the full picture.

## When to use something else

Babel Fishers currently has no web editor, translator accounts or approval workflow. Review happens in your pull requests. If translators or other non-developers need to work on the strings, a platform such as Crowdin or Tolgee is a better fit.

## Documentation

- [Getting started](https://gycks.github.io/babelfishers/getting-started/)
- [Configuration](https://gycks.github.io/babelfishers/guides/configuration/)
- [Translation providers](https://gycks.github.io/babelfishers/guides/providers/)
- [Continuous integration](https://gycks.github.io/babelfishers/guides/ci/)
- [Supported formats](https://gycks.github.io/babelfishers/formats/)
- [CLI reference](https://gycks.github.io/babelfishers/reference/cli/)

## Feedback

Questions and ideas go to [Discussions](https://github.com/Gycks/babelfishers/discussions), bugs to [issues](https://github.com/Gycks/babelfishers/issues).

## Contributing

This project is still young and worked on when time allows. If you find a bug or have an idea, open an issue and I will take a look.

## License

[Apache License 2.0](LICENSE)