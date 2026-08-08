from sqlalchemy.orm import Session

from app.ai.conversation_formatter import format_conversation
from app.ai.intent_detector import (
    Intent,
    detect_intent,
)
from app.ai.memory_extractor import extract_memory, extract_memories
from app.ai.memory_retriever import MemoryRetriever
from app.ai.prompt_builder import build_prompt
from app.ai.summary_generator import generate_summary
from app.repositories.chat_repository import ChatRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import (
    create_message,
    get_messages_for_ai,
)
from app.services.ai_service import generate_ai_response
from app.services.summary_service import summary_service


chat_repository = ChatRepository()
memory_repository = MemoryRepository()
memory_retriever = MemoryRetriever()


def ask_ai(
    db: Session,
    chat_id: int,
    content: str,
) -> str:

    # -------------------------
    # Detect User Intent
    # -------------------------

    intent = detect_intent(content)

    # -------------------------
    # Remember Intent
    # -------------------------

    if intent == Intent.REMEMBER:

        chat = chat_repository.get_by_id(
            db=db,
            chat_id=chat_id,
        )

        if chat is None:
            raise ValueError("Chat not found")

        memory_data = extract_memory(content)

        memory_repository.create_ai_memory(
            db=db,
            workspace_id=chat.workspace_id,
            memory_data=memory_data,
        )

        return "🧠 Memory has been saved successfully."

    # -------------------------
    # Save Summary Intent
    # -------------------------

    if intent == Intent.SAVE_SUMMARY:

        chat = chat_repository.get_by_id(
            db=db,
            chat_id=chat_id,
        )

        if chat is None:
            raise ValueError("Chat not found")

        history = get_messages_for_ai(
            db=db,
            chat_id=chat_id,
        )

        conversation = format_conversation(history)

        summary = generate_summary(
            conversation,
        )

        memory_repository.create_summary(
            db=db,
            workspace_id=chat.workspace_id,
            summary=summary,
        )

        return "✅ Conversation summary has been saved to workspace memory."

    # -------------------------
    # Save User Message
    # -------------------------

    create_message(
        db=db,
        chat_id=chat_id,
        role="user",
        content=content,
    )

    # -------------------------
    # Load Chat
    # -------------------------

    chat = chat_repository.get_by_id(
        db=db,
        chat_id=chat_id,
    )

    if chat is None:
        raise ValueError("Chat not found")

    # -------------------------
    # Retrieve Relevant Memories
    # -------------------------

    memories = memory_retriever.retrieve(
        db=db,
        workspace_id=chat.workspace_id,
        query=content,
        limit=5,
    )

    # -------------------------
    # Load Chat History
    # -------------------------

    history = get_messages_for_ai(
        db=db,
        chat_id=chat_id,
    )

    # -------------------------
    # Automatic Conversation Summary
    # -------------------------

    message_count = len(history)

    conversation_summary = summary_service.get_summary(
        db=db,
        chat_id=chat_id,
    )

    last_summary_count = (
        conversation_summary.message_count
        if conversation_summary
        else None
    )

    print("=" * 60)
    print(f"Chat ID: {chat_id}")
    print(f"Message Count: {message_count}")
    print(f"Last Summary Count: {last_summary_count}")

    if summary_service.should_generate_summary(
        message_count=message_count,
        last_summary_count=last_summary_count,
    ):

        print(">>> GENERATING SUMMARY <<<")

        conversation = format_conversation(
            history,
        )

        summary = generate_summary(
            conversation,
        )

        print("Generated Summary:")
        print(summary)

        summary_service.save_summary(
            db=db,
            chat_id=chat_id,
            summary=summary,
            message_count=message_count,
        )

        print(">>> SUMMARY SAVED <<<")

        conversation_summary = summary_service.get_summary(
            db=db,
            chat_id=chat_id,
        )
    # -------------------------
    # Build Prompt
    # -------------------------

    prompt = build_prompt(
        memories=memories,
        conversation_summary=conversation_summary,
        history=history,
    )
    print("=" * 60)
    print("RETRIEVED MEMORIES:")
    for memory in memories:
        print(memory.title, ":", memory.content)

    print("=" * 60)

    print("FINAL PROMPT:")
    print(prompt)
    print("=" * 60)

    # -------------------------
    # Generate AI Response
    # -------------------------

    ai_reply = generate_ai_response(
        prompt,
    )

    # -------------------------
    # Save Assistant Response
    # -------------------------

    create_message(
        db=db,
        chat_id=chat_id,
        role="assistant",
        content=ai_reply,
    )


    # -------------------------
    # Automatic Memory Extraction
    # -------------------------

    try:

        extracted_memories = extract_memories(
            content
        )
        print(
            "AUTO MEMORIES:",
            extracted_memories
        )

        if extracted_memories:

            memory_repository.create_multiple_ai_memories(
                db=db,
                workspace_id=chat.workspace_id,
                memories=extracted_memories,
            )

    except Exception as e:

        print(
            "Automatic memory extraction failed:",
            e,
        )


    return ai_reply