from datetime import datetime

from pydantic import BaseModel, Field

from app.models.workspace_memory import (
    MemorySource,
    MemoryStatus,
    MemoryType,
)


class MemoryCreate(BaseModel):
    memory_type: MemoryType
    title: str = Field(..., max_length=200)
    content: str
    importance: int = Field(
        default=5,
        ge=1,
        le=10,
    )


class MemoryUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=200,
    )

    content: str | None = None

    importance: int | None = Field(
        default=None,
        ge=1,
        le=10,
    )


class MemoryResponse(BaseModel):
    id: int
    workspace_id: int

    memory_type: MemoryType

    title: str
    content: str

    importance: int
    confidence: float

    source: MemorySource
    status: MemoryStatus

    expires_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }