from datetime import datetime

from pydantic import BaseModel


class ChatCreate(BaseModel):
    title: str


class ChatResponse(BaseModel):
    id: int
    title: str
    workspace_id: int
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }