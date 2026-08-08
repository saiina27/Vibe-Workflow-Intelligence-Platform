from enum import Enum


class Intent(str, Enum):
    CHAT = "chat"
    SAVE_SUMMARY = "save_summary"
    REMEMBER = "remember"


SAVE_SUMMARY_KEYWORDS = [
    "save this conversation",
    "save this chat",
    "summarize and save",
    "summary and save",
    "save summary",
]

REMEMBER_KEYWORDS = [
    "remember this",
    "remember that",
    "remember",
    "don't forget",
    "save this",
    "pin this",
    "pin this discussion",
]


def detect_intent(
    message: str,
) -> Intent:

    text = message.lower().strip()

    for keyword in SAVE_SUMMARY_KEYWORDS:
        if keyword in text:
            return Intent.SAVE_SUMMARY

    for keyword in REMEMBER_KEYWORDS:
        if keyword in text:
            return Intent.REMEMBER

    return Intent.CHAT