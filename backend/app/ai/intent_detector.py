from enum import Enum


class Intent(str, Enum):
    CHAT = "chat"
    SAVE_SUMMARY = "save_summary"
    REMEMBER = "remember"


SAVE_SUMMARY_KEYWORDS = (
    "save this conversation",
    "save this chat",
    "summarize and save",
    "summary and save",
    "save summary",
)


# These phrases represent an explicit request to STORE information.
# Keep them specific so normal questions containing words like
# "remember" do not accidentally trigger the memory-save flow.
REMEMBER_KEYWORDS = (
    "remember this",
    "remember that",
    "remember my",
    "remember that i",
    "remember that we",
    "don't forget",
    "do not forget",
    "save this information",
    "save this preference",
    "save this detail",
    "save this fact",
    "pin this",
    "pin this discussion",
)


def detect_intent(message: str) -> Intent:
    """
    Detect explicit application-level intents.

    Important:
    Memory retrieval/search is intentionally NOT classified as
    REMEMBER. Retrieval requests should remain CHAT so that the
    Sprint 11 tool-calling engine can select MemoryTool.

    Examples:

        "Remember that I use Python"
            -> REMEMBER

        "What do you remember about me?"
            -> CHAT

        "Search my workspace memory"
            -> CHAT

        "Save this conversation"
            -> SAVE_SUMMARY
    """

    text = message.lower().strip()

    if not text:
        return Intent.CHAT

    # --------------------------------------------------------
    # 1. Explicit conversation-summary save
    # --------------------------------------------------------

    for keyword in SAVE_SUMMARY_KEYWORDS:
        if keyword in text:
            return Intent.SAVE_SUMMARY

    # --------------------------------------------------------
    # 2. Explicit memory-save request
    # --------------------------------------------------------

    for keyword in REMEMBER_KEYWORDS:
        if keyword in text:
            return Intent.REMEMBER

    # --------------------------------------------------------
    # 3. Everything else remains CHAT.
    #
    # This is important for Sprint 11:
    #
    # "What do you remember about me?"
    # "Search my memory"
    # "Find my documents"
    # "Search the web"
    #
    # must reach the LLM/tool-calling layer.
    # --------------------------------------------------------

    return Intent.CHAT