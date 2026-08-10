import logging

from sqlalchemy.orm import Session

from app.services.memory_cleanup_service import (
    memory_cleanup_service,
)

from app.ai.conversation_formatter import format_conversation
from app.ai.intent_detector import (
    Intent,
    detect_intent,
)
from app.ai.memory_extractor import (
    extract_memory,
    extract_memories,
)
from app.ai.memory_retriever import MemoryRetriever
from app.ai.prompt_builder import build_prompt
from app.ai.summary_generator import generate_summary
from app.ai.chat_title_generator import ChatTitleGenerator
from app.ai.topic_detector import TopicDetector
from app.ai.knowledge_retriever import KnowledgeRetriever

from app.repositories.chat_repository import ChatRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import (
    create_message,
    get_messages_for_ai,
)

from app.services.ai_service import generate_ai_response
from app.services.summary_service import summary_service
from app.services.memory_decision_service import (
    MemoryDecisionService,
)


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

def debug_separator(title: str):
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
# ASK AI
# ============================================================

def ask_ai(
    db: Session,
    chat_id: int,
    content: str,
) -> str:

    debug_separator("ASK AI START")

    logger.info("Chat ID: %s", chat_id)
    logger.info(
        "User message: %s",
        debug_preview(content),
    )
    logger.info(
        "User message length: %s",
        len(content),
    )

    # ========================================================
    # MEMORY CLEANUP
    # ========================================================

    try:

        logger.info(
            "[1] Starting memory cleanup..."
        )

        memory_cleanup_service.expire_memories(db)

        logger.info(
            "[1] Memory cleanup completed."
        )

    except Exception:

        logger.exception(
            "[1] Memory cleanup failed."
        )

    # ========================================================
    # DETECT USER INTENT
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
    # REMEMBER INTENT
    # ========================================================

    if intent == Intent.REMEMBER:

        debug_separator("REMEMBER INTENT")

        try:

            logger.info(
                "Loading chat for memory creation..."
            )

            chat = chat_repository.get_by_id(
                db=db,
                chat_id=chat_id,
            )

            if chat is None:

                logger.error(
                    "Chat not found. Chat ID: %s",
                    chat_id,
                )

                raise ValueError("Chat not found")

            logger.info(
                "Chat found. Workspace ID: %s",
                chat.workspace_id,
            )

            logger.info(
                "Extracting memory..."
            )

            memory_data = extract_memory(content)

            logger.info(
                "Extracted memory: %s",
                memory_data,
            )

            memory_repository.create_ai_memory(
                db=db,
                workspace_id=chat.workspace_id,
                memory_data=memory_data,
            )

            logger.info(
                "Memory saved successfully."
            )

            return "🧠 Memory has been saved successfully."

        except Exception:

            logger.exception(
                "REMEMBER intent failed."
            )

            raise

    # ========================================================
    # SAVE SUMMARY INTENT
    # ========================================================

    if intent == Intent.SAVE_SUMMARY:

        debug_separator("SAVE SUMMARY INTENT")

        try:

            logger.info(
                "Loading chat..."
            )

            chat = chat_repository.get_by_id(
                db=db,
                chat_id=chat_id,
            )

            if chat is None:

                logger.error(
                    "Chat not found. Chat ID: %s",
                    chat_id,
                )

                raise ValueError("Chat not found")

            logger.info(
                "Workspace ID: %s",
                chat.workspace_id,
            )

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
                history,
            )

            logger.info(
                "Conversation length: %s",
                len(conversation),
            )

            logger.info(
                "Generating summary..."
            )

            summary = generate_summary(
                conversation,
            )

            logger.info(
                "Generated summary:\n%s",
                debug_preview(summary, 1500),
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
                "SAVE_SUMMARY intent failed."
            )

            raise

    # ========================================================
    # SAVE USER MESSAGE
    # ========================================================

    debug_separator("SAVE USER MESSAGE")

    try:

        logger.info(
            "Saving user message..."
        )

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
    # LOAD CHAT
    # ========================================================

    debug_separator("LOAD CHAT")

    try:

        logger.info(
            "Loading chat ID: %s",
            chat_id,
        )

        chat = chat_repository.get_by_id(
            db=db,
            chat_id=chat_id,
        )

        if chat is None:

            logger.error(
                "Chat not found."
            )

            raise ValueError("Chat not found")

        logger.info(
            "Chat loaded successfully."
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
            "Failed to load chat."
        )

        raise

    # ========================================================
    # AUTOMATIC CHAT TITLE
    # ========================================================

    if chat.title == "New Chat":

        debug_separator("AUTOMATIC CHAT TITLE")

        try:

            logger.info(
                "Generating automatic chat title..."
            )

            generated_title = chat_title_generator.generate(
                conversation=f"User: {content}"
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
    # AUTOMATIC CHAT TOPIC
    # ========================================================

    if chat.topic is None:

        debug_separator("AUTOMATIC CHAT TOPIC")

        try:

            logger.info(
                "Detecting chat topic..."
            )

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

    else:

        logger.info(
            "Existing topic found: %s",
            chat.topic,
        )

    # ========================================================
    # RETRIEVE RELEVANT MEMORIES
    # ========================================================

    debug_separator("MEMORY RETRIEVAL")

    try:

        logger.info(
            "Retrieving relevant memories..."
        )

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
                getattr(memory, "title", None),
                debug_preview(
                    getattr(memory, "content", None),
                    300,
                ),
            )

    except Exception:

        logger.exception(
            "Memory retrieval failed."
        )

        memories = []

    # ========================================================
    # RAG KNOWLEDGE RETRIEVAL
    # ========================================================

    debug_separator("RAG KNOWLEDGE RETRIEVAL")

    try:

        logger.info(
            "Retrieving knowledge chunks..."
        )

        logger.info(
            "Workspace ID: %s",
            chat.workspace_id,
        )

        logger.info(
            "Query: %s",
            debug_preview(content),
        )

        knowledge_chunks = knowledge_retriever.retrieve(
            db=db,
            workspace_id=chat.workspace_id,
            query=content,
            limit=5,
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
                getattr(chunk, "chunk_index", None),
                debug_preview(
                    getattr(chunk, "text", None),
                    500,
                ),
            )

    except Exception:

        logger.exception(
            "Knowledge retrieval failed."
        )

        knowledge_chunks = []

    # ========================================================
    # LOAD CHAT HISTORY
    # ========================================================

    debug_separator("CHAT HISTORY")

    try:

        logger.info(
            "Loading chat history..."
        )

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
    # AUTOMATIC CONVERSATION SUMMARY
    # ========================================================

    debug_separator("CONVERSATION SUMMARY")

    message_count = len(history)

    logger.info(
        "Message count: %s",
        message_count,
    )

    try:

        conversation_summary = summary_service.get_summary(
            db=db,
            chat_id=chat_id,
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
    # SUMMARY DECISION
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
    # GENERATE SUMMARY
    # ========================================================

    if should_generate_summary:

        debug_separator("GENERATING SUMMARY")

        try:

            logger.info(
                "Formatting conversation..."
            )

            conversation = format_conversation(
                history,
            )

            logger.info(
                "Conversation length: %s",
                len(conversation),
            )

            logger.info(
                "Calling generate_summary()..."
            )

            summary = generate_summary(
                conversation,
            )

            logger.info(
                "Summary generation completed."
            )

            logger.info(
                "Generated summary:\n%s",
                debug_preview(summary, 1500),
            )

            if not summary:

                logger.warning(
                    "Summary generator returned EMPTY result."
                )

            logger.info(
                "Saving summary..."
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

            logger.info(
                "Summary reloaded from database: %s",
                conversation_summary is not None,
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
    # BUILD PROMPT
    # ========================================================

    debug_separator("PROMPT BUILDING")

    try:

        logger.info(
            "Memories: %s",
            len(memories),
        )

        logger.info(
            "Knowledge chunks: %s",
            len(knowledge_chunks),
        )

        logger.info(
            "History messages: %s",
            len(history),
        )

        logger.info(
            "Summary available: %s",
            conversation_summary is not None,
        )

        prompt = build_prompt(
            memories=memories,
            conversation_summary=conversation_summary,
            history=history,
            knowledge_chunks=knowledge_chunks,
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
            debug_preview(prompt, 3000),
        )

    except Exception:

        logger.exception(
            "Prompt building failed."
        )

        raise

    # ========================================================
    # GENERATE AI RESPONSE
    # ========================================================

    debug_separator("AI RESPONSE GENERATION")

    try:

        logger.info(
            "Calling generate_ai_response()..."
        )

        ai_reply = generate_ai_response(
            prompt,
        )

        logger.info(
            "AI response generated successfully."
        )

        logger.info(
            "AI reply length: %s",
            len(ai_reply),
        )

        logger.info(
            "RAG FINAL AI RESPONSE:\n%s",
            debug_preview(ai_reply, 2000),
        )

    except Exception:

        logger.exception(
            "AI response generation failed."
        )

        raise

    # ========================================================
    # SAVE ASSISTANT RESPONSE
    # ========================================================

    debug_separator("SAVE ASSISTANT RESPONSE")

    try:

        logger.info(
            "Saving assistant response..."
        )

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
    # AUTOMATIC MEMORY EXTRACTION
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

            logger.info(
                "Processing extracted memories..."
            )

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

        # Memory extraction should not break
        # the main AI response.

    # ========================================================
    # COMPLETE
    # ========================================================

    debug_separator("ASK AI COMPLETE")

    logger.info(
        "Chat ID %s completed successfully.",
        chat_id,
    )

    logger.info(
        "Final AI reply:\n%s",
        debug_preview(ai_reply, 2000),
    )

    return ai_reply