from google import genai

from app.ai.memory_parser import parse_memory
from app.core.config import settings
from app.ai.gateway import AIGateway

client = genai.Client(
    api_key=settings.gemini_api_key,
)


def extract_memory(
    text: str,
) -> dict:

    prompt = f"""
You are an AI memory extraction engine.

Extract exactly ONE useful memory.

Return ONLY valid JSON.

Example:

{{
    "memory_type":"preference",
    "title":"Preferred Backend",
    "content":"User prefers FastAPI.",
    "importance":5
}}

User Message:

{text}

Ignore command words like:
- remember this
- save this
- remember

Extract only the actual information the user wants to save.
"""

    try:

        gateway = AIGateway()
        response = gateway.generate(prompt)

        return parse_memory(response)

    except Exception:

        return {
            "memory_type": "knowledge",
            "title": "Memory",
            "content": text,
            "importance": 3,
        }

def extract_memories(
    text: str,
) -> list[dict]:

    prompt = f"""
You are an AI memory extraction engine.

Extract useful long-term memories from the user's message.

Return ONLY valid JSON.

Format:

{{
    "memories": [
        {{
            "memory_type": "goal",
            "title": "Memory title",
            "content": "Memory content",
            "importance": 5
        }}
    ]
}}

Rules:

Extract only:
- goals
- preferences
- facts
- decisions
- projects
- important user information

Ignore:
- greetings
- temporary questions
- commands like remember/save this

User Message:

{text}
"""

    try:

        gateway = AIGateway()

        response = gateway.generate(prompt)

        data = parse_memory(response)

        return data.get(
            "memories",
            []
        )

    except Exception:

        return []    