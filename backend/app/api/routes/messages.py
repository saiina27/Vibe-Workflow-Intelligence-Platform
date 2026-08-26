from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.message import MessageCreate, MessageResponse
from app.services.auth_service import get_current_user
from app.services.conversation_service import ask_ai
from app.services.message_service import get_chat_messages


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
    ask_ai(
        db=db,
        chat_id=chat_id,
        content=request.content,
        user_id=current_user.id,
    )

    messages = get_chat_messages(
        db,
        chat_id,
    )

    return messages[-1]

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