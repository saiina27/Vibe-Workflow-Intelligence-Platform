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

Required format:

{{
    "memory_type": "preference",
    "title": "Preferred Programming Language",
    "content": "User prefers Python.",
    "importance": 5
}}

Allowed memory_type values:
- fact
- preference
- profile
- goal
- decision
- task
- knowledge
- summary
- working
- project

Rules:

1. Ignore command words such as:
   - remember this
   - save this
   - remember

2. Extract only the actual information the user wants to save.

3. Keep the content concise and factual.

4. Return exactly one memory object.

5. Always include:
   - memory_type
   - title
   - content
   - importance

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

        parsed = parse_memory(
            response.content
        )

        # ----------------------------------------------------
        # NORMALIZE AI RESPONSE
        # ----------------------------------------------------

        if not isinstance(parsed, dict):
            raise ValueError(
                "Memory extractor returned an invalid object."
            )

        # Support accidental {"memories": [...]} response.
        if "memories" in parsed:

            memories = parsed.get("memories")

            if not memories:
                raise ValueError(
                    "Memory extractor returned no memory."
                )

            parsed = memories[0]

        if not isinstance(parsed, dict):
            raise ValueError(
                "Extracted memory is not a valid object."
            )

        memory_type = str(
            parsed.get(
                "memory_type",
                "knowledge",
            )
        ).strip().lower()

        # ----------------------------------------------------
        # NORMALIZE MEMORY TYPE
        # ----------------------------------------------------

        allowed_types = {
            "fact",
            "preference",
            "profile",
            "goal",
            "decision",
            "task",
            "knowledge",
            "summary",
            "working",
            "project",
        }

        if memory_type not in allowed_types:
            memory_type = "knowledge"

        title = str(
            parsed.get(
                "title",
                "Memory",
            )
        ).strip()

        content = str(
            parsed.get(
                "content",
                text,
            )
        ).strip()

        importance = parsed.get(
            "importance",
            5,
        )

        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 5

        importance = max(
            1,
            min(
                importance,
                10,
            ),
        )

        if not title:
            title = "Memory"

        if not content:
            content = text.strip()

        return {
            "memory_type": memory_type,
            "title": title[:200],
            "content": content,
            "importance": importance,
        }

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
- fact
- preference
- profile
- goal
- decision
- task
- knowledge
- summary
- working
- project

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