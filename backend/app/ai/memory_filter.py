import re

# Words that suggest the user is stating something about themselves,
# their project or a decision. Without any of them the extraction LLM
# call is skipped, because it would only return an empty list.
MARKERS = {
    "i", "im", "my", "mine", "we", "our", "ours",
    "humne", "hum", "hamara", "hamare", "hamari",
    "mera", "meri", "mere", "main", "mai", "maine", "mujhe",
    "decided", "decision", "prefer", "remember", "yaad",
}


def worth_extracting(text: str) -> bool:
    """False only for messages that clearly state nothing about the user."""

    if not text or not text.strip():
        return False

    # Other scripts (for example Hindi in Devanagari): always try.
    if any(ord(ch) > 127 and ch.isalpha() for ch in text):
        return True

    words = {
        w.replace("'", "")
        for w in re.findall(r"[a-z']+", text.lower())
    }

    return bool(words & MARKERS)
