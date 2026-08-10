from datetime import datetime

from pydantic import BaseModel, ConfigDict
from app.models.knowledge_source import KnowledgeStatus


class KnowledgeSourceResponse(BaseModel):
    id: int
    workspace_id: int
    title: str
    filename: str
    file_type: str
    file_size: int
    status: KnowledgeStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class KnowledgeUploadResponse(BaseModel):
    message: str
    source: KnowledgeSourceResponse


class KnowledgeChunkResponse(BaseModel):
    id: int
    chunk_index: int
    text: str
    chunk_metadata: dict

    model_config = ConfigDict(
        from_attributes=True,
    )
    
class KnowledgeListItem(BaseModel):
    id: int
    workspace_id: int
    title: str
    filename: str
    file_type: str
    file_size: int
    status: KnowledgeStatus
    created_at: datetime
    updated_at: datetime
    chunk_count: int

    model_config = ConfigDict(
        from_attributes=True,
    )
