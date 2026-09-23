# Translation providers

Babel Fishers does not translate text by itself. It sends your text to a provider that you choose. You use your own account and you pay the provider directly.

## Choose a provider

Set the provider in the `[engine]` section of `babelfishers.toml`.

```toml
[engine]
provider = "deepl"
```

These are the values you can use.

| Provider | Config value       | Type |
|---|--------------------|---|
| DeepL | `deepl`            | Translation service |
| Azure AI Translator | `azure`            | Translation service |
| Google Cloud Translation | `google-translate` | Translation service |
| LibreTranslate | `libre-translate`  | Translation service |
| OpenAI | `openai`           | AI model |
| Anthropic | `anthropic`        | AI model |
| Google Gemini | `google`           | AI model |
| Mistral | `mistral`          | AI model |
| DeepSeek | `deepseek`         | AI model |

The two types differ in one way. A translation service only needs an account key. An AI model also needs a model ID, because you choose which model does the work.

## Use a different provider for some files

The provider in `[engine]` is the default. You can override it for a group of files with the `engine` option.

```toml
[engine]
provider = "deepl"

[resources.json]
paths = [
  "locales/[source]/*.json",
  { path = "legal/[source]/*.json", engine = "anthropic" },
]
```

Here the files in `legal` go to Anthropic and everything else goes to DeepL. If Anthropic fails for those files, Babel Fishers falls back to DeepL. A name that is not a valid provider is reported as a warning.

## Set your credentials

Every provider reads its settings from environment variables. They all start with `BF_`. Set them in your shell or in the secret settings of your CI system. Babel Fishers does not read `.env` files.

!!! warning "Keep keys out of your repository"

    Never write an API key into `babelfishers.toml` or any file you commit.

| Provider | Variable | Required | What it holds |
|---|---|---|---|
| DeepL | `BF_DEEPL_API_KEY` | Yes | Your DeepL API key. |
| Azure AI Translator | `BF_AZURE_API_KEY` | Yes | Your Azure key. |
| | `BF_AZURE_REGION` | Yes | The region of your Azure resource. |
| | `BF_AZURE_ENDPOINT` | No | A custom endpoint. |
| Google Cloud Translation | `BF_GOOGLE_PROJECT_ID` | Yes | Your Google Cloud project ID. |
| | `BF_GOOGLE_LOCATION` | No | The location to use. The default is `global`. |
| | `BF_GOOGLE_APPLICATION_CREDENTIALS` | No | The path to a service account key file. |
| LibreTranslate | `BF_LIBRETRANSLATE_URL` | Yes | The address of your LibreTranslate server. |
| | `BF_LIBRETRANSLATE_API_KEY` | No | The key for that server, if it needs one. |
| OpenAI | `BF_OPENAI_API_KEY` | Yes | Your OpenAI key. |
| | `BF_OPENAI_MODEL_ID` | Yes | The model to use. |
| Anthropic | `BF_ANTHROPIC_API_KEY` | Yes | Your Anthropic key. |
| | `BF_ANTHROPIC_MODEL_ID` | Yes | The model to use. |
| Google Gemini | `BF_GOOGLE_API_KEY` | Yes | Your Google AI key. |
| | `BF_GOOGLE_MODEL_ID` | Yes | The model to use. |
| Mistral | `BF_MISTRAL_API_KEY` | Yes | Your Mistral key. |
| | `BF_MISTRAL_MODEL_ID` | Yes | The model to use. |
| DeepSeek | `BF_DEEPSEEK_API_KEY` | Yes | Your DeepSeek key. |
| | `BF_DEEPSEEK_MODEL_ID` | Yes | The model to use. |

Babel Fishers does not pick a model for you. Take the model ID from the documentation of your provider.

!!! note "Two Google options"

    `google-translate` is the Google Cloud Translation service. `google` is the Gemini AI model. They are separate providers with separate settings.

## What to know before you choose

- **Your text is sent to the provider.** Only the translatable text is sent. Placeholders are protected first. Every provider except LibreTranslate is a cloud service. With LibreTranslate you can run the server yourself and keep everything on your own machine.
- **Some providers receive context.** Notes and comments from your files, such as gettext translator comments or Apple comments, are passed along as context. DeepL and the AI models use them. Azure, Google Cloud Translation and LibreTranslate do not.
- **Rate limits are handled.** When a provider says you are sending too much, Babel Fishers waits and tries again, up to three times. The wait grows each time.
- **Failures are retried.** If a translation fails, Babel Fishers tries once more. If it still fails and you set a different provider for those files, it switches to your default provider.
- **A final failure stops the run.** A wrong key, an exhausted quota or a refused request ends with an error. Fix the cause and run the command again. Files that already finished are recorded, so they are not translated a second time.
