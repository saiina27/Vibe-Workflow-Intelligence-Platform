import json
import re


def parse_memory(
    ai_response: str,
) -> dict:
    """
    Convert AI JSON response into a Python dictionary.
    Handles both plain JSON and ```json ... ``` responses.
    """

    if not ai_response:
        return {}

    cleaned_response = ai_response.strip()

    # Remove markdown code fences
    cleaned_response = re.sub(
        r"^```json\s*",
        "",
        cleaned_response,
        flags=re.IGNORECASE,
    )

    cleaned_response = re.sub(
        r"^```\s*",
        "",
        cleaned_response,
    )

    cleaned_response = re.sub(
        r"\s*```$",
        "",
        cleaned_response,
    )

    cleaned_response = cleaned_response.strip()

    try:

        return json.loads(
            cleaned_response
        )

    except json.JSONDecodeError as e:

        print(
            f"Memory JSON parsing failed: {e}"
        )

        return {
            "memory_type": "knowledge",
            "title": "Memory",
            "content": cleaned_response,
            "importance": 3,
        }