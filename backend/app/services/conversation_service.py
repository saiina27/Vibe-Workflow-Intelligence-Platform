import logging
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

            # Re-fetch the authorized chat after rollback.
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

        logger.info(
            "Workspace ID: %s",
            chat.workspace_id,
        )

        logger.info(
            "Query: %s",
            debug_preview(content),
        )

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

        if history:

            logger.info(
                "Last message: %s",
                debug_preview(
                    getattr(
                        history[-1],
                        "content",
                        None,
                    ),
                    300,
                ),
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

    logger.info(
        "Message count: %s",
        message_count,
    )

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

            logger.info(
                "Existing summary:\n%s",
                debug_preview(
                    conversation_summary.summary,
                    1500,
                ),
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

            logger.info(
                "Conversation length: %s",
                len(conversation),
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

            logger.info(
                "Summary saved successfully."
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
            "Prompt built successfully."
        )

        logger.info(
            "Prompt length: %s",
            len(prompt),
        )

        logger.info(
            "FINAL PROMPT PREVIEW:\n%s",
            debug_preview(
                prompt,
                3000,
            ),
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

        logger.info(
            "Calling generate_ai_response_with_tools()..."
        )

        logger.info(
            "Tool context workspace ID: %s",
            tool_context.workspace_id,
        )

        logger.info(
            "Tool context user ID: %s",
            tool_context.user_id,
        )

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

        logger.info(
            "AI reply length: %s",
            len(ai_reply),
        )

        logger.info(
            "FINAL AI RESPONSE:\n%s",
            debug_preview(
                ai_reply,
                2000,
            ),
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

        logger.info(
            "Extracting automatic memories..."
        )

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

    logger.info(
        "Final AI reply:\n%s",
        debug_preview(
            ai_reply,
            2000,
        ),
    )

    return ai_reply