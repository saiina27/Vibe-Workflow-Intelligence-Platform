from app.ai.gateway import AIGateway
from app.schemas.ai import AIRequest
from app.models.enums import TaskComplexity, TaskType


class TopicDetector:

    ALLOWED_TOPICS = {
        "AI Engineering",
        "Backend Development",
        "Frontend Development",
        "Database",
        "DevOps",
        "Programming",
        "Interview Preparation",
        "Data Science",
        "Project Management",
        "General",
    }

    def __init__(self):
        self.gateway = AIGateway()

    def detect(
        self,
        message: str,
    ) -> str:

        if not message.strip():
            return "General"

        topics = ", ".join(self.ALLOWED_TOPICS)

        prompt = f"""
Classify the following user message into exactly ONE topic.

Allowed topics:
{topics}

Rules:
- Return exactly one topic from the allowed list.
- Do not explain your answer.
- Do not return markdown.
- Do not create a new topic.
- Choose General if no topic clearly fits.

User message:
{message}
""".strip()

        request = AIRequest(
            prompt=prompt,
            task_type=TaskType.UNKNOWN,
            complexity=TaskComplexity.SIMPLE,
            temperature=0.0,
            max_tokens=20,
        )

        response = self.gateway.generate(request)

        detected_topic = response.content.strip()

        if detected_topic in self.ALLOWED_TOPICS:
            return detected_topic

        return "General"