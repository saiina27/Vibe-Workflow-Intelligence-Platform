from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.chat import ChatCreate, ChatResponse
from app.services.auth_service import get_current_user
from app.services.chat_service import (
    create_chat,
    get_workspace_chats,
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
        db,
        workspace_id,
        request.title,
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
        db,
        workspace_id,
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
    )

    return {
        "response": response,
    }