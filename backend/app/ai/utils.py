from app.models.message import Message


def build_conversation(
    messages: list[Message],
):
    conversation = []

    for message in messages:
        conversation.append(
            {
                "role": message.role,
                "parts": [message.content],
            }
        )

    return conversation