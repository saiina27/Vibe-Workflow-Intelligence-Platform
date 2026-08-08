from enum import Enum


class TaskType(str, Enum):
    CHAT = "CHAT"

    CODE = "CODE"

    DOCUMENT = "DOCUMENT"

    ANALYSIS = "ANALYSIS"

    DECISION = "DECISION"

    SUGGESTION = "SUGGESTION"

    MEMORY = "MEMORY"

    SEARCH = "SEARCH"

    IMAGE = "IMAGE"

    UNKNOWN = "UNKNOWN"