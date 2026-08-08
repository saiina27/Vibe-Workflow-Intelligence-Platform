from app.ai.gateway import AIGateway
from app.ai.task_classifier import task_classifier
from app.schemas.ai import AIRequest


gateway = AIGateway()


def generate_ai_response(
    prompt: str,
) -> str:

    task_type = task_classifier.classify(
        prompt
    )

    request = AIRequest(
        prompt=prompt,
        task_type=task_type,
    )

    response = gateway.generate(
        request
    )

    return response.content