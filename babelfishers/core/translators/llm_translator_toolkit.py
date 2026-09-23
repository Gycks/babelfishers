from pydantic import BaseModel


_SYSTEM_PROMPT_TEMPLATE = """
## Role
You are a professional translator. Preserve the meaning, tone, and register of the source text.

## Task
Translate the text from {source} to {target}.
Preserve all formatting, whitespace, and punctuation from the source text.
If a context hint is provided, use it to inform the translation; otherwise translate on your own judgment.

## Style
Do not introduce em dashes or en dashes into the translation. Only use one if the source text already has
one at that point, and even then prefer whatever punctuation reads naturally in the target language.

## Output format
Return only the translated text: no preamble, no explanation, no surrounding quotes. This holds whether the
response is returned as plain text or in a structured field.{tag_handling}"""

_TAG_HANDLING_TEMPLATE = """

## Tag handling
The text may contain protected spans wrapped in tags shaped like:
{tag_shapes}

For example, in `Contact <gls id="1">Jane Doe</gls> now.`, only the surrounding words are translated: the tag,
its attributes, and everything between its open and close are copied through unchanged."""


def build_system_prompt(source: str, target: str, ignore_tag_shapes: list[str]) -> str:
    tag_handling = ""
    if ignore_tag_shapes:
        tag_handling = _TAG_HANDLING_TEMPLATE.format(tag_shapes="\n".join(ignore_tag_shapes))

    return _SYSTEM_PROMPT_TEMPLATE.format(source=source, target=target, tag_handling=tag_handling)


def build_user_prompt(text: str, context_hint: str | None = None) -> str:
    prompt = f"Text to translate:\n{text}"

    if context_hint:
        prompt += f"\n\nContext hint:\n{context_hint}"

    return prompt


class ModelTranslationResponse(BaseModel):
    translation: str
