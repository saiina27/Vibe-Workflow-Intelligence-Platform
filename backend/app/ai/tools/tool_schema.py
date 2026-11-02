from app.schemas.ai import ToolDefinition

MAX_DESCRIPTION = 160
MAX_PARAM_DESCRIPTION = 80

# Keys that only cost tokens. (Property NAMES are never touched: they are
# handled separately below, so a parameter called "title" is kept.)
DROP_KEYS = {"title", "examples", "example", "$comment", "$schema"}

# Values of these keys are copied as they are.
KEEP_AS_IS = {
    "type", "enum", "const", "default", "required", "format", "pattern",
    "minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength",
}


def shorten(text: str | None, limit: int) -> str:
    """Whitespace-normalised text cut at a sentence end, or a word end."""

    text = " ".join((text or "").split())

    if len(text) <= limit:
        return text

    cut = text[:limit]
    sentence_end = max(cut.rfind(". "), cut.rfind("; "), cut.rfind("? "))

    if sentence_end >= 40:
        return cut[: sentence_end + 1]

    word_end = cut.rfind(" ")

    if word_end >= 40:
        cut = cut[:word_end]

    return cut.rstrip(",;:. ") + "..."


def compact_schema(node, limit: int = MAX_PARAM_DESCRIPTION):
    """A JSON-schema copy with shorter descriptions and no noise keys."""

    if isinstance(node, list):
        return [compact_schema(item, limit) for item in node]

    if not isinstance(node, dict):
        return node

    out = {}

    for key, value in node.items():
        if key in DROP_KEYS:
            continue

        if key == "description" and isinstance(value, str):
            out[key] = shorten(value, limit)

        elif key == "properties" and isinstance(value, dict):
            out[key] = {
                name: compact_schema(sub, limit) for name, sub in value.items()
            }

        elif key in KEEP_AS_IS:
            out[key] = value

        else:
            out[key] = compact_schema(value, limit)

    return out


def compact_definition(definition: ToolDefinition) -> ToolDefinition:
    return ToolDefinition(
        name=definition.name,
        description=shorten(definition.description, MAX_DESCRIPTION),
        parameters=compact_schema(definition.parameters),
    )
