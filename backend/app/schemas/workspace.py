from datetime import datetime

from pydantic import BaseModel


class WorkspaceCreate(BaseModel):
    name: str
    description: str | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class WorkspaceRename(BaseModel):
    name: str
