import logging
from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.chat_title_generator import ChatTitleGenerator
from app.ai.conversation_formatter import format_conversation
from app.ai.intent_detector import (
    Intent,
    detect_intent,
)
from app.ai.knowledge_retriever import KnowledgeRetriever
from app.ai.memory_extractor import (
    extract_memories,
    extract_memory,
)
from app.ai.memory_retriever import MemoryRetriever
from app.ai.prompt_builder import build_prompt
from app.ai.summary_generator import generate_summary
from app.ai.topic_detector import TopicDetector
from app.ai.tools.context import ToolContext

from app.models.workspace import Workspace

from app.repositories.chat_repository import ChatRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import (
    create_message,
    get_messages_for_ai,
)

from app.services.ai_service import (
    generate_ai_response_stream,
    generate_ai_response_stream_with_tools,
    generate_ai_response_with_tools,
)
from app.services.memory_cleanup_service import (
    memory_cleanup_service,
)
from app.services.memory_decision_service import (
    MemoryDecisionService,
)
from app.services.summary_service import summary_service
from app.schemas.workspace_memory import MemoryCreate
from app.schemas.ai import AIStreamEvent


# ============================================================
# LOGGER
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# SERVICES
# ============================================================

chat_repository = ChatRepository()
memory_repository = MemoryRepository()
memory_decision_service = MemoryDecisionService()
memory_retriever = MemoryRetriever()


def _is_memory_confirmation_request(
    db,
    chat_id: int,
) -> bool:
    """
    Check whether the latest assistant message is asking
    the user to confirm saving a specific memory.
    """

    history = get_messages_for_ai(
        db=db,
        chat_id=chat_id,
    )

    if not history:
        return False

    latest_assistant = next(
        (
            message
            for message in reversed(history)
            if getattr(message, "role", None) == "assistant"
        ),
        None,
    )

    if latest_assistant is None:
        return False

    content = (
        getattr(latest_assistant, "content", "")
        or ""
    ).lower()

    return (
        "remember this specific detail" in content
        and "future chats" in content
    )


def _is_confirmation_response(content: str) -> bool:
    """
    Recognize a concise yes/no response to a pending
    memory confirmation.
    """

    normalized = (
        content.strip()
        .lower()
        .rstrip(".!?")
    )

    return normalized in {
        "yes",
        "y",
        "yeah",
        "yep",
        "sure",
        "okay",
        "ok",
        "no",
        "n",
        "nope",
        "nah",
    }


def _is_positive_confirmation(content: str) -> bool:
    normalized = (
        content.strip()
        .lower()
        .rstrip(".!?")
    )

    return normalized in {
        "yes",
        "y",
        "yeah",
        "yep",
        "sure",
        "okay",
        "ok",
    }


def _get_previous_user_message(
    db,
    chat_id: int,
) -> str | None:
    """
    Return the user message immediately before the
    current confirmation response.
    """

    history = get_messages_for_ai(
        db=db,
        chat_id=chat_id,
    )

    if len(history) < 2:
        return None

    current_index = len(history) - 1

    if getattr(history[current_index], "role", None) != "user":
        return None

    for message in reversed(
        history[:current_index]
    ):
        if getattr(message, "role", None) == "user":
            return getattr(message, "content", None)

    return None
chat_title_generator = ChatTitleGenerator()
topic_detector = TopicDetector()
knowledge_retriever = KnowledgeRetriever()


# ============================================================
# DEBUG HELPERS
# ============================================================

def debug_separator(title: str) -> None:
    logger.info("")
    logger.info("=" * 70)
    logger.info(title)
    logger.info("=" * 70)


def debug_preview(
    text,
    limit: int = 500,
) -> str:

    if text is None:
        return "<EMPTY>"

    text = str(text)

    if len(text) > limit:
        return text[:limit] + "... [TRUNCATED]"

    return text


# ============================================================
# CHAT ACCESS VALIDATION
# ============================================================

def _get_authorized_chat(
    db: Session,
    chat_id: int,
    user_id: int,
):
    """
    Load a chat and verify that its workspace belongs
    to the authenticated user.

    IMPORTANT:
    This validation happens before:
        - user message persistence
        - memory retrieval
        - RAG retrieval
        - tool context creation
        - tool execution
        - AI generation
    """

    chat = chat_repository.get_by_id(
        db=db,
        chat_id=chat_id,
    )

    if chat is None:

        logger.error(
            "Chat not found. Chat ID: %s",
            chat_id,
        )

        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    workspace = (
        db.query(Workspace)
        .filter(
            Workspace.id == chat.workspace_id,
            Workspace.user_id == user_id,
        )
        .first()
    )

    if workspace is None:

        logger.error(
            "Workspace ownership validation failed. "
            "User ID: %s, Workspace ID: %s",
            user_id,
            chat.workspace_id,
        )

        # Do not reveal whether the chat exists
        # when it belongs to another user's workspace.
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    logger.info(
        "Workspace ownership validated. "
        "User ID: %s, Workspace ID: %s",
        user_id,
        chat.workspace_id,
    )

    return chat


# ============================================================
# ASK AI
# ============================================================

async def ask_ai(
    db: Session,
    chat_id: int,
    content: str,
    user_id: int,
) -> str:

    debug_separator("ASK AI START")

    logger.info(
        "Chat ID: %s",
        chat_id,
    )

    logger.info(
        "User ID: %s",
        user_id,
    )

    logger.info(
        "User message: %s",
        debug_preview(content),
    )

    logger.info(
        "User message length: %s",
        len(content),
    )

    # ========================================================
    # 1. CHAT ACCESS VALIDATION
    # ========================================================

    debug_separator("CHAT ACCESS VALIDATION")

    try:

        chat = _get_authorized_chat(
            db=db,
            chat_id=chat_id,
            user_id=user_id,
        )

        logger.info(
            "Chat access validated successfully."
        )

        logger.info(
            "Workspace ID: %s",
            chat.workspace_id,
        )

        logger.info(
            "Chat title: %s",
            chat.title,
        )

        logger.info(
            "Chat topic: %s",
            chat.topic,
        )

    except Exception:

        logger.exception(
            "Chat access validation failed."
        )

        raise

    # ========================================================
    # 2. REQUEST-SCOPED TOOL CONTEXT
    # ========================================================

    debug_separator("TOOL CONTEXT")

    tool_context = ToolContext(
        db=db,
        workspace_id=chat.workspace_id,
        user_id=user_id,
    )

    logger.info(
        "Request-scoped ToolContext created."
    )

    logger.info(
        "Tool workspace ID: %s",
        tool_context.workspace_id,
    )

    logger.info(
        "Tool user ID: %s",
        tool_context.user_id,
    )

    # ========================================================
    # 3. MEMORY CLEANUP
    # ========================================================

    try:

        logger.info(
            "[1] Starting memory cleanup..."
        )

        memory_cleanup_service.expire_memories(
            db
        )

        logger.info(
            "[1] Memory cleanup completed."
        )

    except Exception:

        logger.exception(
            "[1] Memory cleanup failed. "
            "Continuing request."
        )

    # ========================================================
    # 4. INTENT DETECTION
    # ========================================================

    try:

        logger.info(
            "[2] Detecting user intent..."
        )

        intent = detect_intent(content)

        logger.info(
            "[2] Detected intent: %s",
            intent,
        )

    except Exception:

        logger.exception(
            "[2] Intent detection failed."
        )

        raise

    # ========================================================
    # 5. REMEMBER INTENT
    # ========================================================

    if intent == Intent.REMEMBER:

        debug_separator("REMEMBER INTENT")

        try:

            logger.info(
                "Extracting explicit memory..."
            )

            memory_data = extract_memory(
                content
            )

            logger.info(
                "Extracted memory: %s",
                memory_data,
            )

            memory = MemoryCreate(
                memory_type=memory_data["memory_type"],
                title=memory_data["title"],
                content=memory_data["content"],
                importance=memory_data.get(
                    "importance",
                    5,
                ),
            )

            memory_decision_service.process_memory(
                db=db,
                workspace_id=chat.workspace_id,
                memory=memory,
            )

            logger.info(
                "Explicit memory saved successfully."
            )

            return (
                "🧠 Memory has been saved successfully."
            )

        except Exception:

            logger.exception(
                "REMEMBER intent failed."
            )

            raise

    # ========================================================
    # 6. SAVE SUMMARY INTENT
    # ========================================================

    if intent == Intent.SAVE_SUMMARY:

        debug_separator("SAVE SUMMARY INTENT")

        try:

            logger.info(
                "Loading conversation history..."
            )

            history = get_messages_for_ai(
                db=db,
                chat_id=chat_id,
            )

            logger.info(
                "History count: %s",
                len(history),
            )

            conversation = format_conversation(
                history
            )

            logger.info(
                "Conversation length: %s",
                len(conversation),
            )

            logger.info(
                "Generating summary..."
            )

            summary = generate_summary(
                conversation
            )

            logger.info(
                "Generated summary:\n%s",
                debug_preview(
                    summary,
                    1500,
                ),
            )

            memory_repository.create_summary(
                db=db,
                workspace_id=chat.workspace_id,
                summary=summary,
            )

            logger.info(
                "Workspace summary saved successfully."
            )

            return (
                "✅ Conversation summary has been "
                "saved to workspace memory."
            )

        except Exception:

            logger.exception(
                "SAVE SUMMARY intent failed."
            )

            raise

    # ========================================================
    # 7. SAVE USER MESSAGE
    # ========================================================

    debug_separator("SAVE USER MESSAGE")

    try:

        create_message(
            db=db,
            chat_id=chat_id,
            role="user",
            content=content,
        )

        logger.info(
            "User message saved successfully."
        )

    except Exception:

        logger.exception(
            "Failed to save user message."
        )

        raise

    # ========================================================
    # 8. AUTOMATIC CHAT TITLE
    # ========================================================

    if chat.title == "New Chat":

        debug_separator("AUTOMATIC CHAT TITLE")

        try:

            generated_title = (
                chat_title_generator.generate(
                    conversation=f"User: {content}"
                )
            )

            logger.info(
                "Generated title: %s",
                generated_title,
            )

            if generated_title:

                chat_repository.update_title(
                    db=db,
                    chat=chat,
                    title=generated_title,
                )

                logger.info(
                    "Chat title updated successfully."
                )

            else:

                logger.warning(
                    "Title generator returned empty result."
                )

        except Exception:

            logger.exception(
                "Automatic chat title generation failed."
            )

    else:

        logger.info(
            "Existing chat title found. "
            "Skipping title generation."
        )

    # ========================================================
    # 9. AUTOMATIC CHAT TOPIC
    # ========================================================

    if chat.topic is None:

        debug_separator("AUTOMATIC CHAT TOPIC")

        try:

            detected_topic = topic_detector.detect(
                message=content,
            )

            logger.info(
                "Detected topic: %s",
                detected_topic,
            )

            chat.topic = detected_topic

            db.commit()
            db.refresh(chat)

            logger.info(
                "Chat topic saved successfully."
            )

        except Exception:

            logger.exception(
                "Automatic chat topic detection failed."
            )

            db.rollback()

            chat = _get_authorized_chat(
                db=db,
                chat_id=chat_id,
                user_id=user_id,
            )

    else:

        logger.info(
            "Existing topic found: %s",
            chat.topic,
        )

    # ========================================================
    # 10. MEMORY RETRIEVAL
    # ========================================================

    debug_separator("MEMORY RETRIEVAL")

    try:

        memories = memory_retriever.retrieve(
            db=db,
            workspace_id=chat.workspace_id,
            query=content,
            limit=5,
        )

        logger.info(
            "Retrieved memory count: %s",
            len(memories),
        )

        for index, memory in enumerate(
            memories,
            start=1,
        ):

            logger.info(
                "Memory %s | title=%s | content=%s",
                index,
                getattr(
                    memory,
                    "title",
                    None,
                ),
                debug_preview(
                    getattr(
                        memory,
                        "content",
                        None,
                    ),
                    300,
                ),
            )

    except Exception:

        logger.exception(
            "Memory retrieval failed."
        )

        memories = []

    # ========================================================
    # 11. RAG KNOWLEDGE RETRIEVAL
    # ========================================================

    debug_separator("RAG KNOWLEDGE RETRIEVAL")

    try:

        knowledge_chunks = (
            knowledge_retriever.retrieve(
                db=db,
                workspace_id=chat.workspace_id,
                query=content,
                limit=5,
            )
        )

        logger.info(
            "Retrieved knowledge chunks: %s",
            len(knowledge_chunks),
        )

        if not knowledge_chunks:

            logger.warning(
                "RAG returned ZERO knowledge chunks."
            )

        for index, chunk in enumerate(
            knowledge_chunks,
            start=1,
        ):

            logger.info(
                "Chunk %s | DB index=%s | text=%s",
                index,
                getattr(
                    chunk,
                    "chunk_index",
                    None,
                ),
                debug_preview(
                    getattr(
                        chunk,
                        "text",
                        None,
                    ),
                    500,
                ),
            )

    except Exception:

        logger.exception(
            "Knowledge retrieval failed."
        )

        knowledge_chunks = []

    # ========================================================
    # 12. LOAD CHAT HISTORY
    # ========================================================

    debug_separator("CHAT HISTORY")

    try:

        history = get_messages_for_ai(
            db=db,
            chat_id=chat_id,
        )

        logger.info(
            "History message count: %s",
            len(history),
        )

    except Exception:

        logger.exception(
            "Failed to load chat history."
        )

        raise

    # ========================================================
    # 13. LOAD CONVERSATION SUMMARY
    # ========================================================

    debug_separator("CONVERSATION SUMMARY")

    message_count = len(history)

    try:

        conversation_summary = (
            summary_service.get_summary(
                db=db,
                chat_id=chat_id,
            )
        )

        if conversation_summary:

            last_summary_count = (
                conversation_summary.message_count
            )

            logger.info(
                "Existing summary found."
            )

            logger.info(
                "Last summary message count: %s",
                last_summary_count,
            )

        else:

            last_summary_count = None

            logger.info(
                "No existing conversation summary."
            )

    except Exception:

        logger.exception(
            "Failed to load conversation summary."
        )

        conversation_summary = None
        last_summary_count = None

    # ========================================================
    # 14. SUMMARY DECISION
    # ========================================================

    try:

        should_generate_summary = (
            summary_service.should_generate_summary(
                message_count=message_count,
                last_summary_count=last_summary_count,
            )
        )

        logger.info(
            "Should generate summary: %s",
            should_generate_summary,
        )

    except Exception:

        logger.exception(
            "Summary decision failed."
        )

        should_generate_summary = False

    # ========================================================
    # 15. GENERATE SUMMARY
    # ========================================================

    if should_generate_summary:

        debug_separator("GENERATING SUMMARY")

        try:

            conversation = format_conversation(
                history
            )

            summary = generate_summary(
                conversation
            )

            if not summary:

                logger.warning(
                    "Summary generator returned EMPTY result."
                )

            summary_service.save_summary(
                db=db,
                chat_id=chat_id,
                summary=summary,
                message_count=message_count,
            )

            conversation_summary = (
                summary_service.get_summary(
                    db=db,
                    chat_id=chat_id,
                )
            )

        except Exception:

            logger.exception(
                "Automatic conversation summary "
                "generation failed."
            )

            conversation_summary = None

    else:

        logger.info(
            "Summary generation skipped."
        )

    # ========================================================
    # 16. BUILD PROMPT
    # ========================================================

    debug_separator("PROMPT BUILDING")

    try:

        prompt = build_prompt(
            memories=memories,
            conversation_summary=conversation_summary,
            history=history,
            knowledge_chunks=knowledge_chunks,
            include_memories=False,
            include_knowledge=False,
        )

        logger.info(
            "Prompt built successfully. Length: %s",
            len(prompt),
        )

    except Exception:

        logger.exception(
            "Prompt building failed."
        )

        raise

    # ========================================================
    # 17. GENERATE AI RESPONSE WITH TOOLS
    # ========================================================

    debug_separator("AI RESPONSE + TOOL CALLING")

    try:

        ai_reply = (
            await generate_ai_response_with_tools(
                prompt=prompt,
                context=tool_context,
            )
        )

        if ai_reply is None:

            raise ValueError(
                "AI gateway returned an empty response."
            )

        ai_reply = str(ai_reply)

        logger.info(
            "AI response generated successfully."
        )

    except Exception:

        logger.exception(
            "AI response generation failed."
        )

        raise

    # ========================================================
    # 18. SAVE ASSISTANT RESPONSE
    # ========================================================

    debug_separator("SAVE ASSISTANT RESPONSE")

    try:

        create_message(
            db=db,
            chat_id=chat_id,
            role="assistant",
            content=ai_reply,
        )

        logger.info(
            "Assistant response saved successfully."
        )

    except Exception:

        logger.exception(
            "Failed to save assistant response."
        )

        raise

    # ========================================================
    # 19. AUTOMATIC MEMORY EXTRACTION
    # ========================================================

    debug_separator("AUTOMATIC MEMORY EXTRACTION")

    try:

        extracted_memories = extract_memories(
            content
        )

        logger.info(
            "AUTO MEMORIES: %s",
            extracted_memories,
        )

        if extracted_memories:

            memory_decision_service.process_memories(
                db=db,
                workspace_id=chat.workspace_id,
                memories=extracted_memories,
            )

            logger.info(
                "Automatic memories processed successfully."
            )

        else:

            logger.info(
                "No automatic memories detected."
            )

    except Exception:

        logger.exception(
            "Automatic memory extraction failed."
        )

        # Memory extraction must never break
        # an otherwise successful AI response.

    # ========================================================
    # 20. COMPLETE
    # ========================================================

    debug_separator("ASK AI COMPLETE")

    logger.info(
        "Chat ID %s completed successfully.",
        chat_id,
    )

    return ai_reply


# ============================================================
# STREAMING ASK AI
# ============================================================

def stream_ai_response(
    db: Session,
    chat_id: int,
    content: str,
    user_id: int,
    with_tools: bool = False,
) -> Iterator[str]:
    """
    Stream an AI response while preserving the normal
    conversation lifecycle.

    IMPORTANT:

    This is the Phase 3 streaming path.

    Existing ask_ai() remains the normal non-streaming
    + tool-calling path.

    Streaming currently streams direct provider text.
    Tool Activity events and streaming tool-calling are
    intentionally left for the next phase.

    Flow:

        Validate Chat
            ↓
        Memory Cleanup
            ↓
        Intent Detection
            ↓
        Save User Message
            ↓
        Title / Topic
            ↓
        Memory Retrieval
            ↓
        RAG Retrieval
            ↓
        History / Summary
            ↓
        Build Prompt
            ↓
        Provider Streaming
            ↓
        Accumulate Response
            ↓
        Save Assistant Message
            ↓
        Automatic Memory Extraction
    """

    debug_separator("STREAMING ASK AI START")

    logger.info(
        "Chat ID: %s | User ID: %s",
        chat_id,
        user_id,
    )

    logger.info(
        "Streaming user message: %s",
        debug_preview(content),
    )

    # ========================================================
    # 1. CHAT ACCESS VALIDATION
    # ========================================================

    chat = _get_authorized_chat(
        db=db,
        chat_id=chat_id,
        user_id=user_id,
    )

    # ========================================================
    # 2. MEMORY CLEANUP
    # ========================================================

    try:

        memory_cleanup_service.expire_memories(
            db
        )

    except Exception:

        logger.exception(
            "Streaming memory cleanup failed. "
            "Continuing request."
        )

    # ========================================================
    # 3. INTENT DETECTION
    # ========================================================

    intent = detect_intent(content)

    # ========================================================
    # 4. SPECIAL INTENTS
    # ========================================================

    # ========================================================
    # MEMORY CONFIRMATION
    # ========================================================

    if (
        _is_confirmation_response(content)
        and _is_memory_confirmation_request(
            db=db,
            chat_id=chat_id,
        )
    ):

        try:

            previous_user_message = (
                _get_previous_user_message(
                    db=db,
                    chat_id=chat_id,
                )
            )

            if _is_positive_confirmation(content):

                if not previous_user_message:
                    raise ValueError(
                        "Unable to recover the memory detail "
                        "for confirmation."
                    )

                memory_data = extract_memory(
                    previous_user_message
                )

                memory = MemoryCreate(
                    memory_type=memory_data["memory_type"],
                    title=memory_data["title"],
                    content=memory_data["content"],
                    importance=memory_data.get(
                        "importance",
                        5,
                    ),
                )

                memory_decision_service.process_memory(
                    db=db,
                    workspace_id=chat.workspace_id,
                    memory=memory,
                )

                message = (
                    "Got it bro, I’ll remember that "
                    "for future chats."
                )

            else:

                message = (
                    "No problem bro, I won’t save it."
                )

            create_message(
                db=db,
                chat_id=chat_id,
                role="user",
                content=content,
            )

            create_message(
                db=db,
                chat_id=chat_id,
                role="assistant",
                content=message,
            )

            yield message
            return

        except Exception:

            logger.exception(
                "Streaming memory confirmation failed."
            )

            raise

    if intent == Intent.REMEMBER:

        # Explicit memory requests continue through the
        # normal AI flow so the assistant can respond
        # conversationally instead of using a canned
        # success message.
        intent = Intent.CHAT

    if intent == Intent.SAVE_SUMMARY:

        try:

            history = get_messages_for_ai(
                db=db,
                chat_id=chat_id,
            )

            conversation = format_conversation(
                history
            )

            summary = generate_summary(
                conversation
            )

            memory_repository.create_summary(
                db=db,
                workspace_id=chat.workspace_id,
                summary=summary,
            )

            message = (
                "✅ Conversation summary has been "
                "saved to workspace memory."
            )

            yield message

            return

        except Exception:

            logger.exception(
                "Streaming SAVE SUMMARY intent failed."
            )

            raise

    # ========================================================
    # 5. SAVE USER MESSAGE
    # ========================================================

    create_message(
        db=db,
        chat_id=chat_id,
        role="user",
        content=content,
    )

    # ========================================================
    # 6. AUTOMATIC CHAT TITLE
    # ========================================================

    if chat.title == "New Chat":

        try:

            generated_title = (
                chat_title_generator.generate(
                    conversation=f"User: {content}"
                )
            )

            if generated_title:

                chat_repository.update_title(
                    db=db,
                    chat=chat,
                    title=generated_title,
                )

        except Exception:

            logger.exception(
                "Streaming automatic title generation failed."
            )

    # ========================================================
    # 7. AUTOMATIC CHAT TOPIC
    # ========================================================

    if chat.topic is None:

        try:

            detected_topic = topic_detector.detect(
                message=content,
            )

            chat.topic = detected_topic

            db.commit()
            db.refresh(chat)

        except Exception:

            logger.exception(
                "Streaming topic detection failed."
            )

            db.rollback()

            chat = _get_authorized_chat(
                db=db,
                chat_id=chat_id,
                user_id=user_id,
            )

    # ========================================================
    # 8. MEMORY RETRIEVAL
    # ========================================================

    try:

        memories = memory_retriever.retrieve(
            db=db,
            workspace_id=chat.workspace_id,
            query=content,
            limit=5,
        )

    except Exception:

        logger.exception(
            "Streaming memory retrieval failed."
        )

        memories = []

    # ========================================================
    # 9. RAG KNOWLEDGE RETRIEVAL
    # ========================================================

    try:

        knowledge_chunks = (
            knowledge_retriever.retrieve(
                db=db,
                workspace_id=chat.workspace_id,
                query=content,
                limit=5,
            )
        )

    except Exception:

        logger.exception(
            "Streaming knowledge retrieval failed."
        )

        knowledge_chunks = []

    # ========================================================
    # 10. LOAD CHAT HISTORY
    # ========================================================

    history = get_messages_for_ai(
        db=db,
        chat_id=chat_id,
    )

    # ========================================================
    # 11. LOAD CONVERSATION SUMMARY
    # ========================================================

    message_count = len(history)

    try:

        conversation_summary = (
            summary_service.get_summary(
                db=db,
                chat_id=chat_id,
            )
        )

        if conversation_summary:

            last_summary_count = (
                conversation_summary.message_count
            )

        else:

            last_summary_count = None

    except Exception:

        logger.exception(
            "Streaming conversation summary retrieval failed."
        )

        conversation_summary = None
        last_summary_count = None

    # ========================================================
    # 12. SUMMARY DECISION
    # ========================================================

    try:

        should_generate_summary = (
            summary_service.should_generate_summary(
                message_count=message_count,
                last_summary_count=last_summary_count,
            )
        )

    except Exception:

        logger.exception(
            "Streaming summary decision failed."
        )

        should_generate_summary = False

    # ========================================================
    # 13. GENERATE SUMMARY
    # ========================================================

    if should_generate_summary:

        try:

            conversation = format_conversation(
                history
            )

            summary = generate_summary(
                conversation
            )

            if summary:

                summary_service.save_summary(
                    db=db,
                    chat_id=chat_id,
                    summary=summary,
                    message_count=message_count,
                )

                conversation_summary = (
                    summary_service.get_summary(
                        db=db,
                        chat_id=chat_id,
                    )
                )

        except Exception:

            logger.exception(
                "Streaming automatic summary generation failed."
            )

            conversation_summary = None

    # ========================================================
    # 14. BUILD PROMPT
    # ========================================================

    prompt = build_prompt(
        memories=memories,
        conversation_summary=conversation_summary,
        history=history,
        knowledge_chunks=knowledge_chunks,
        include_memories=False,
        include_knowledge=False,
    )

    logger.info(
        "Streaming prompt built. Length: %s",
        len(prompt),
    )

    # ========================================================
    # 15. STREAM AI RESPONSE
    # ========================================================

    response_chunks: list[str] = []

    try:

        if with_tools:

            tool_context = ToolContext(
                db=db,
                workspace_id=chat.workspace_id,
                user_id=user_id,
            )

            logger.info(
                "Streaming tool-aware AI response enabled."
            )

            for event in (
                generate_ai_response_stream_with_tools(
                    prompt=prompt,
                    context=tool_context,
                )
            ):

                # --------------------------------------------
                # CONTENT EVENT
                # --------------------------------------------

                if event.type == "content":

                    if not event.text:
                        continue

                    response_chunks.append(
                        event.text
                    )

                    yield event

                    continue

                # --------------------------------------------
                # TOOL LIFECYCLE EVENT
                # --------------------------------------------

                yield event

        else:

            # Existing Phase 3 text streaming path.
            for chunk in generate_ai_response_stream(
                prompt
            ):

                if not chunk:
                    continue

                response_chunks.append(
                    chunk
                )

                yield chunk

    except Exception:

        logger.exception(
            "AI streaming failed."
        )

        raise
    # ========================================================
    # 16. BUILD COMPLETE RESPONSE
    # ========================================================

    ai_reply = "".join(
        response_chunks
    )

    if not ai_reply:

        raise RuntimeError(
            "AI provider returned an empty streaming response."
        )

    logger.info(
        "Streaming completed. Final response length: %s",
        len(ai_reply),
    )

    # ========================================================
    # 17. SAVE ASSISTANT RESPONSE
    # ========================================================

    try:

        create_message(
            db=db,
            chat_id=chat_id,
            role="assistant",
            content=ai_reply,
        )

        logger.info(
            "Streaming assistant response saved successfully."
        )

    except Exception:

        logger.exception(
            "Failed to save streaming assistant response."
        )

        raise

    # ========================================================
    # 18. AUTOMATIC MEMORY EXTRACTION
    # ========================================================

    try:

        extracted_memories = extract_memories(
            content
        )

        if extracted_memories:

            memory_decision_service.process_memories(
                db=db,
                workspace_id=chat.workspace_id,
                memories=extracted_memories,
            )

            logger.info(
                "Streaming automatic memories processed."
            )

    except Exception:

        logger.exception(
            "Streaming automatic memory extraction failed."
        )

        # Memory extraction must never invalidate
        # an otherwise successful AI response.

    # ========================================================
    # 19. COMPLETE
    # ========================================================

    debug_separator("STREAMING ASK AI COMPLETE")

    logger.info(
        "Chat ID %s streaming request completed.",
        chat_id,
    )