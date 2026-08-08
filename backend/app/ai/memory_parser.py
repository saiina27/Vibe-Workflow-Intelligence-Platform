import json


def parse_memory(ai_response: str) -> dict:
    """
    Convert Gemini JSON response into Python dict.
    """

    try:
        return json.loads(ai_response)

    except Exception:
        return {
            "memory_type": "knowledge",
            "title": "Memory",
            "content": ai_response,
            "importance": 3,
        }