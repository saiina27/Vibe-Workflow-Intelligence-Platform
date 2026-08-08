from app.models.message import Message


def format_conversation(
    history: list[Message],
) -> str:

    lines = []

    for message in history:

        role = message.role.capitalize()

        lines.append(
            f"{role}: {message.content}"
        )

    return "\n".join(lines)