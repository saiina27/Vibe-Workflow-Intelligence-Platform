from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.chat import ChatCreate, ChatResponse
from app.dependencies.auth import get_current_user
from app.services.chat_service import (
    create_chat,
    get_workspace_chats,
    archive_chat,
    restore_chat,
    get_chats_by_topic,
    get_chats_by_status,
)
from app.schemas.message import AskRequest, AskResponse
from app.services.conversation_service import ask_ai

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

@router.post(
    "/{chat_id}/ask",
    response_model=AskResponse,
)
def ask_chat(
    workspace_id: int,
    chat_id: int,
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    response = ask_ai(
        db=db,
        chat_id=chat_id,
        content=request.content,
        user_id=current_user.id,
    )

    return {
        "response": response,
    }

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