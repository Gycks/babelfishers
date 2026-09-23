# Quickstart

!!! warning "Prerequisite"

    You need [Babel Fishers installed](installation.md) first.

## 1. Create the project

Run this in the root of your project.

```bash
babelfishers init
```

You will be prompted for a few details to complete the setup. Follow the instructions on screen. In general, you need to provide:

1. **Source locale.** The language your files are written in. The default is `en`.
2. **Target locales.** The languages to translate into, separated by commas. For example `fr,de`.
3. **Translation engine.** The provider that will handle the translation.

The command then shows a review and asks before it writes `babelfishers.toml` in the current folder.

You can skip the questions by passing options. This is useful in scripts.

```bash
babelfishers init --source en --targets fr,de --engine deepl --yes
```

Run `babelfishers locales` to see every locale code you can use.

## 2. Set your provider key

Babel Fishers reads credentials from environment variables. They all start with `BF_`.

=== "macOS and Linux"

    ```bash
    export BF_DEEPL_API_KEY="your-key"
    ```

=== "Windows (PowerShell)"

    ```powershell
    $env:BF_DEEPL_API_KEY = "your-key"
    ```

The example above is for DeepL. Each provider has its own variable names. Find yours on the [Translation providers](../guides/providers.md) page.

!!! warning "Keep keys out of your repository"

    Never write an API key into `babelfishers.toml` or any file you commit.

## 3. List the files to translate

Open `babelfishers.toml`. The `init` command wrote the locale and engine sections. It left a comment where your files go.

Group your files by format. This example translates every JSON file in the `locales/en` folder.

```toml
[locale]
source = "en"
targets = ["fr", "de"]

[engine]
provider = "deepl"

[resources.json]
paths = ["locales/[source]/*.json"]
```

Here is how the paths work.

- `[source]` stands for a locale code. Babel Fishers reads `locales/en/*.json`.
- For each target it writes to the same pattern with that locale. Here that gives `locales/fr/` and `locales/de/`.
- Without `[source]` in the path, the output sits next to the original. `strings.json` becomes `strings_fr.json` and `strings_de.json`.
- The wildcard `*` matches any file name.

The format name after `resources.` tells Babel Fishers how to read the files. Use `json`, `yaml`, `html`, `properties`, `android`, `po`, `apple`, `arb`, `xliff` or `resx`.

## 4. Preview, then translate

Start with a dry run. It shows what would be translated and changes nothing.

```bash
babelfishers translate --dry-run
```

When the plan looks right, run it.

```bash
babelfishers translate
```

Your translated files now exist next to your sources.

## What just happened

Babel Fishers also created a `.babelfishers` folder in your project. It holds two things.

- **The translation memory.** Text that was translated once is stored here. The same text is never sent to your provider twice.
- **A run record.** It notes the last completed run, so the next run knows what changed.

Commit this folder with your project. Then your teammates and your CI reuse the same memory. See [Translation memory](../guides/translation-memory.md) to inspect or clear it.

## Next steps

- Learn every option in [Configuration](../guides/configuration.md).
- Keep product names untranslated with a [glossary](../guides/glossaries.md).
- Understand what happens to your text in [How it works](../concepts/how-it-works.md).
