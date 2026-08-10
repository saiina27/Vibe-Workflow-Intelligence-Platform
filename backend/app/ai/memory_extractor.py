from app.ai.memory_parser import parse_memory
from app.ai.gateway import AIGateway
from app.schemas.ai import AIRequest
from app.models.enums import TaskType, TaskComplexity


def extract_memory(
    text: str,
) -> dict:

    prompt = f"""
You are an AI memory extraction engine.

Extract exactly ONE useful long-term memory from the user's message.

Return ONLY valid JSON.

Format:

{{
    "memory_type": "preference",
    "title": "Preferred Programming Language",
    "content": "User prefers Python.",
    "importance": 5
}}

Allowed memory_type values:
- preference
- knowledge
- fact
- goal
- project
- decision
- task
- summary

Rules:

1. Ignore command words such as:
   - remember this
   - save this
   - remember

2. Extract only the actual information the user wants to save.

3. Keep the content concise and factual.

User Message:

{text}
"""

    try:

        gateway = AIGateway()

        request = AIRequest(
            prompt=prompt,
            task_type=TaskType.CODE,
            complexity=TaskComplexity.SIMPLE,
        )

        response = gateway.generate(
            request
        )

        return parse_memory(
            response.content
        )

    except Exception as e:

        print(
            f"Memory extraction failed: {e}"
        )

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
            "memory_type": "preference",
            "title": "Preferred Programming Language",
            "content": "User prefers Python.",
            "importance": 5
        }}
    ]
}}

Allowed memory_type values:
- preference
- knowledge
- fact
- goal
- project
- decision
- task
- summary

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
- normal questions
- commands like remember/save this

User Message:

{text}
"""

    try:

        gateway = AIGateway()

        request = AIRequest(
            prompt=prompt,
            task_type=TaskType.CODE,
            complexity=TaskComplexity.SIMPLE,
        )

        response = gateway.generate(
            request
        )

        data = parse_memory(
            response.content
        )

        return data.get(
            "memories",
            []
        )

    except Exception as e:

        print(
            f"Automatic memory extraction failed: {e}"
        )

        return []