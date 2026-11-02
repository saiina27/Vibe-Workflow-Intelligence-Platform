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

# A message that starts like this asks or orders something; it does not
# state a fact. ("show the latest commits of my project")
QUESTION_STARTS = {
    "what", "whats", "how", "why", "when", "where", "which", "who", "whom",
    "whose", "can", "could", "would", "should", "is", "are", "was", "were",
    "do", "does", "did", "will", "show", "list", "give", "tell", "explain",
    "search", "find", "summarize", "summarise", "check", "display", "get",
    "fetch", "compare", "describe", "define", "any",
    "kya", "kaun", "kaise", "kyun", "kyu", "kab", "kitna", "kitne", "kahan",
    "batao", "bata", "dikhao", "dikha", "samjhao", "likho",
}

# Kept even when the message is phrased as a question.
STRONG = {"decided", "decision"}

_EXPLICIT_SAVE = re.compile(
    r"\b(remember (that|this)|save this|keep in mind|note that|yaad rakh)"
)


def worth_extracting(text: str) -> bool:
    """False only for messages that clearly state nothing about the user."""

    if not text or not text.strip():
        return False

    # Other scripts (for example Hindi in Devanagari): always try.
    if any(ord(ch) > 127 and ch.isalpha() for ch in text):
        return True

    stripped = text.strip()
    lowered = stripped.lower()

    word_list = [w.replace("'", "") for w in re.findall(r"[a-z']+", lowered)]
    words = set(word_list)

    asks = stripped.endswith("?") or (
        bool(word_list) and word_list[0] in QUESTION_STARTS
    )

    if asks:
        return bool(words & STRONG) or (
            bool(_EXPLICIT_SAVE.search(lowered)) and not stripped.endswith("?")
        )

    return bool(words & MARKERS) or bool(_EXPLICIT_SAVE.search(lowered))
