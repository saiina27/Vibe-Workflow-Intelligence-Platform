import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.chat import ChatCreate, ChatResponse, ChatRename
from app.dependencies.auth import get_current_user
from app.services.chat_service import (
    create_chat,
    get_workspace_chats,
    archive_chat,
    restore_chat,
    get_chats_by_topic,
    get_chats_by_status,
    delete_chat,
    rename_chat,
)
from app.schemas.message import AskRequest, AskResponse
from app.services.conversation_service import (
    ask_ai,
    stream_ai_response,
)


router = APIRouter(
    prefix="/workspaces/{workspace_id}/chats",
    tags=["Chats"],
)


@router.post(
    "",
    response_model=ChatResponse,
)
def create_new_chat(
    workspace_id: int,
    request: ChatCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_chat(
        db=db,
        workspace_id=workspace_id,
        title=request.title,
        user_id=current_user.id,
    )


@router.get(
    "",
    response_model=list[ChatResponse],
)
def list_chats(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_workspace_chats(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )


@router.delete(
    "/{chat_id}",
)
def delete_workspace_chat(
    workspace_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    delete_chat(
        db=db,
        workspace_id=workspace_id,
        chat_id=chat_id,
        user_id=current_user.id,
    )

    return {
        "message": "Chat deleted successfully",
    }


@router.patch(
    "/{chat_id}",
    response_model=ChatResponse,
)
def rename_workspace_chat(
    workspace_id: int,
    chat_id: int,
    chat_data: ChatRename,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return rename_chat(
        db=db,
        workspace_id=workspace_id,
        chat_id=chat_id,
        user_id=current_user.id,
        title=chat_data.title,
    )


# ============================================================
# NORMAL CHAT
# ============================================================

@router.post(
    "/{chat_id}/ask",
    response_model=AskResponse,
)
async def ask_chat(
    workspace_id: int,
    chat_id: int,
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    response = await ask_ai(
        db=db,
        chat_id=chat_id,
        content=request.content,
        user_id=current_user.id,
    )

    return {
        "response": response,
    }


# ============================================================
# STREAMING CHAT
# ============================================================

@router.post(
    "/{chat_id}/ask/stream",
)
def ask_chat_stream(
    workspace_id: int,
    chat_id: int,
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Stream an AI response using Server-Sent Events.

    Supports:

        content
        tool_start
        tool_done
        tool_error
        done
        error
    """

    def event_stream():
        try:

            for event in stream_ai_response(
                db=db,
                chat_id=chat_id,
                content=request.content,
                user_id=current_user.id,
                with_tools=True,
            ):

                if not event:
                    continue

                # ------------------------------------------------
                # LEGACY STRING CONTENT
                # ------------------------------------------------

                if isinstance(event, str):

                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "content",
                                "text": event,
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

                    continue

                # ------------------------------------------------
                # AI STREAM EVENT
                # ------------------------------------------------

                payload = {
                    "type": event.type,
                }

                if event.text is not None:
                    payload["text"] = event.text

                if event.tool_call_id is not None:
                    payload["tool_call_id"] = event.tool_call_id

                if event.tool_name is not None:
                    payload["tool_name"] = event.tool_name

                if event.duration_ms is not None:
                    payload["duration_ms"] = event.duration_ms

                if event.error is not None:
                    payload["error"] = event.error

                yield (
                    "data: "
                    + json.dumps(
                        payload,
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

            # ------------------------------------------------
            # STREAM COMPLETE
            # ------------------------------------------------

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                    }
                )
                + "\n\n"
            )

        except Exception as exc:

            error_text = str(exc)

            # Some providers (seen with Groq's smaller
            # fallback model) occasionally emit malformed
            # tool-call output that fails to parse. This is a
            # transient model quirk, not a real server error,
            # so show the user something actionable instead of
            # the raw provider error text.
            if (
                "parse" in error_text.lower()
                and "tool call" in error_text.lower()
            ) or "failed_generation" in error_text.lower():

                error_text = (
                    "The AI model had trouble formatting that "
                    "response. Please try asking again — "
                    "rephrasing slightly often helps."
                )

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "message": error_text,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# ARCHIVE / RESTORE
# ============================================================

@router.patch(
    "/{chat_id}/archive",
    response_model=ChatResponse,
)
def archive_workspace_chat(
    workspace_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return archive_chat(
        db=db,
        workspace_id=workspace_id,
        chat_id=chat_id,
        user_id=current_user.id,
    )


@router.patch(
    "/{chat_id}/restore",
    response_model=ChatResponse,
)
def restore_workspace_chat(
    workspace_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return restore_chat(
        db=db,
        workspace_id=workspace_id,
        chat_id=chat_id,
        user_id=current_user.id,
    )


# ============================================================
# FILTERS
# ============================================================

@router.get(
    "/topic/{topic}",
    response_model=list[ChatResponse],
)
def chats_by_topic(
    workspace_id: int,
    topic: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_chats_by_topic(
        db,
        workspace_id,
        topic,
        current_user.id,
    )


@router.get(
    "/status/{status}",
    response_model=list[ChatResponse],
)
def chats_by_status(
    workspace_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_chats_by_status(
        db,
        workspace_id,
        status,
        current_user.id,
    )