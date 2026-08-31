from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user
from app.services.knowledge_retrieval_service import (
    KnowledgeRetrievalService,
)

router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Test"],
)

retrieval_service = KnowledgeRetrievalService()


@router.get("/search")
def search_knowledge(
    workspace_id: int,
    query: str,
    top_k: int = 5,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    chunks = retrieval_service.retrieve(
        db=db,
        workspace_id=workspace_id,
        query=query,
        top_k=top_k,
    )

    return {
        "query": query,
        "count": len(chunks),
        "results": [
            {
                "id": chunk.id,
                "source_id": chunk.knowledge_source_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "metadata": chunk.chunk_metadata,
            }
            for chunk in chunks
        ],
    }