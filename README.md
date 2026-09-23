<img src="docs/assets/banner.svg" alt="Babel Fishers. Localization on your terms." width="640">

Translate your app without breaking it.

Babel Fishers translates your localization files with the provider you choose. It protects placeholders and other parts that must never change. You pay your provider directly, and only for what you use.

Full documentation, including guides for every feature, lives at [gycks.github.io/babelfishers](https://gycks.github.io/babelfishers/).

## Install

```bash
pip install babelfishers
```

Requires Python 3.11 or newer.

## Quickstart

```bash
babelfishers init
babelfishers translate --dry-run
babelfishers translate
```

`init` asks for your source locale, your target locales and a translation provider, then writes `babelfishers.toml`. Add the files to translate under `[resources.<format>]`, set your provider's API key as an environment variable, and run `translate`.

See the [Quickstart](https://gycks.github.io/babelfishers/getting-started/quickstart/) for the full walkthrough.

```toml
[locale]
source = "en"
targets = ["fr", "de", "es"]

[engine]
provider = "deepl"

[resources.json]
paths = ["locales/[source]/*.json"]
```

## What you get

- **Ten file formats.** JSON, HTML, YAML, Java properties, Android strings, gettext, Apple strings, Flutter ARB, XLIFF, and .NET resx. Each parser follows its own format's rules.
- **Nine translation providers.** DeepL, Azure, Google Cloud Translation, LibreTranslate, OpenAI, Anthropic, Google Gemini, Mistral, and DeepSeek. Pick one as your default, or set a different provider per group of files.
- **Placeholders stay intact.** Variables such as `%s` and `{name}`, and plural rules, are protected before translation and checked afterward.
- **Glossaries.** Keep terms untranslated, fix their translation per language, or pass extra context to the provider.
- **A local translation memory.** Text that was translated once is never sent to a provider twice.
- **A dry run.** `translate --dry-run` shows what would happen without calling a provider or writing a file.
- **Continuous integration.** `babelfishers ci` runs a translation in your pipeline and opens or updates a pull request with the result, for GitHub Actions and GitLab CI/CD.

## How it works

Babel Fishers reads your project from one TOML file. It parses each source file once, protects placeholders and glossary terms, sends only the translatable text to your chosen provider, and writes the result back in the same format as the source.

You run Babel Fishers yourself, on your own files, with your own account at the provider you choose. No file has to leave your machine unless you pick a cloud provider. With a self-hosted LibreTranslate server, none does.

See [How it works](https://gycks.github.io/babelfishers/concepts/how-it-works/) for the full picture.

## Documentation

- [Getting started](https://gycks.github.io/babelfishers/getting-started/)
- [Configuration](https://gycks.github.io/babelfishers/guides/configuration/)
- [Translation providers](https://gycks.github.io/babelfishers/guides/providers/)
- [Continuous integration](https://gycks.github.io/babelfishers/guides/ci/)
- [Supported formats](https://gycks.github.io/babelfishers/formats/)
- [CLI reference](https://gycks.github.io/babelfishers/reference/cli/)

## Contributing

This project is still young and worked on when time allows. If you find a bug or have an idea, open an issue and I will take a look.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
