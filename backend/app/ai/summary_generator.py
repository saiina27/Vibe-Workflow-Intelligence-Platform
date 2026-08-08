
from app.ai.gateway import AIGateway

def generate_summary(
    conversation: str,
) -> str:

    prompt = f"""
You are an AI assistant.

Summarize the following conversation.

Rules:
- Keep it concise.
- Preserve important technical decisions.
- Preserve project progress.
- Preserve future action items.
- Return plain text only.

Conversation:

{conversation}
"""

    try:
        gateway = AIGateway()
        response = gateway.generate(prompt)

        return response

    except Exception:
        return (
            "Conversation Summary\n\n"
            "AI summary could not be generated because "
            "the AI service is temporarily unavailable."
        )