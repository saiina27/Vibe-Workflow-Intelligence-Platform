
from datetime import datetime

from pydantic import BaseModel


class ChatCreate(BaseModel):
    title: str | None = None


class ChatRename(BaseModel):
    title: str


class ChatResponse(BaseModel):
    id: int
    title: str
    workspace_id: int
    topic: str | None
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None

    model_config = {
        "from_attributes": True,
    }

