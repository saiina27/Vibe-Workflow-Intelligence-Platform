from datetime import datetime

from pydantic import BaseModel


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    chat_id: int
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }

class AskRequest(BaseModel):
    content: str


class AskResponse(BaseModel):
    response: str    
