from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.message import MessageCreate, MessageResponse
from app.services.auth_service import get_current_user
from app.services.message_service import (
    create_user_message,
    get_chat_messages,
)

router = APIRouter(
    prefix="/chats/{chat_id}/messages",
    tags=["Messages"],
)


@router.post(
    "",
    response_model=MessageResponse,
)
def create_message(
    chat_id: int,
    request: MessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_user_message(
        db,
        chat_id,
        request.content,
    )


@router.get(
    "",
    response_model=list[MessageResponse],
)
def list_messages(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_chat_messages(
        db,
        chat_id,
    )