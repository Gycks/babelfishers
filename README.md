# Babel Fishers

A free, self-hosted localization engine. You run it yourself, on your own files, with your own translation provider account. No account with a translation SaaS company is required, and no file ever has to leave your machine unless you choose a cloud translation provider.

## Why this exists

Most localization platforms ask you to upload your content to their servers and pay per word, per user, or per project. That is a reasonable business for them to run, but it is not always what a smaller project or a privacy conscious team needs. Babel Fishers parses your source files, protects the parts that should never be translated, sends only the translatable text to a translation provider, and writes the result back into a file shaped exactly like your original.

## Supported formats

Babel Fishers supports ten formats today.

| Format | File extension |
|---|---|
| JSON | .json |
| HTML | .html |
| YAML | .yaml, .yml |
| Java properties | .properties |
| Android strings | .xml |
| gettext | .po |
| Apple strings | .strings |
| Flutter ARB | .arb |
| XLIFF | .xliff, .xlf, both versions 1.2 and 2.0 |
| .NET resx | .resx |

Each format parser understands the format's own conventions. 
See the documentation for details on each one.

## How it works

You describe your project in one TOML configuration file. It lists your source locale, your target locales, your translation provider, and the file paths you want translated, grouped by format.

Babel Fishers parses each source file once, then translates it into every target locale you asked for. Placeholders like `%s` or `{name}` are protected before anything is sent to a translation provider, so they always survive intact. If you provide a glossary of terms that should never be translated, or that need a fixed translation, that is respected too. Repeated text is cached locally, so translating the same string twice never costs a second translation call.

## Contributing

This project is still early and moving fast, so expect rough edges. If you find a bug or have an idea, open an issue and I will take a look.

## License

This project does not have a license file yet. Until one is added, all rights are reserved by the author.
