from app.ai.tools.registry import ToolRegistry

CORE_TOOLS = {"search_memory", "search_knowledge", "search_web"}

GITHUB_DOWN_MESSAGE = (
    "GitHub isn't available right now. If you haven't connected it yet, "
    "use the GitHub button at the top. Otherwise GitHub's server did not "
    "respond: please try again in a moment."
)

GITHUB_DOWN_NOTE = (
    "GITHUB IS UNAVAILABLE RIGHT NOW: its tools could not be loaded. Do not "
    "call GitHub tools and do not search the web for GitHub data. Use the "
    "tools you have, and tell the user that GitHub could not be reached.\n\n"
)

_MARKER = "=========================\nCURRENT CONVERSATION"


def github_unavailable(prompt: str, registry) -> bool:
    """The question needs GitHub, but no GitHub tool is registered."""

    needs_github, _ = ToolRegistry.mcp_needs(prompt)

    if not needs_github:
        return False

    return not any(
        getattr(tool, "plugin_name", None) == "github"
        for tool in registry.list_tools()
    )


def only_core_tools(names) -> bool:
    """True when nothing but the general tools is left for the model."""

    return set(names) <= CORE_TOOLS


def add_github_down_note(prompt: str) -> str:
    """Put the note in the system part, above the conversation, so it is
    never mistaken for the user's own message."""

    if _MARKER in prompt:
        return prompt.replace(_MARKER, GITHUB_DOWN_NOTE + _MARKER, 1)

    return GITHUB_DOWN_NOTE + prompt
