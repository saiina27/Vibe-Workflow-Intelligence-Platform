from typing import List
from pydantic import BaseModel


class ExtractedMemory(BaseModel):
    memory_type: str
    content: str


class MemoryExtractionResponse(BaseModel):
    memories: List[ExtractedMemory]