from app.ai.gateway import AIGateway
from app.schemas.ai import AIRequest
from app.models.enums import TaskComplexity, TaskType


class ChatTitleGenerator:

    def __init__(self):
        self.gateway = AIGateway()

    def generate(
        self,
        conversation: str,
    ) -> str | None:

        if not conversation.strip():
            return None

        prompt = f"""
Generate a concise title for the conversation below.

Rules:
- Maximum 60 characters
- Prefer 3 to 8 words
- Describe the main topic of the conversation
- Do not use quotes
- Do not use markdown
- Do not add explanations
- Return only the title

Conversation:
{conversation}
""".strip()

        request = AIRequest(
            prompt=prompt,
            task_type=TaskType.UNKNOWN,
            complexity=TaskComplexity.SIMPLE,
            temperature=0.2,
            max_tokens=30,
        )

        response = self.gateway.generate(request)

        title = response.content.strip()

        if not title:
            return None

        title = title.strip("\"'")

        if len(title) > 60:
            title = title[:60].rsplit(" ", 1)[0]

        return title