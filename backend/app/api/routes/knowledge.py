from pathlib import Path
import shutil

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.schemas.knowledge import (
    KnowledgeListItem,
    KnowledgeUploadResponse,
)
from app.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from app.services.knowledge_service import KnowledgeService
from app.services.workspace_service import require_workspace_access


router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge",
    tags=["Knowledge"],
)


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


ingestion_service = KnowledgeIngestionService()
knowledge_service = KnowledgeService()


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".docx",
}


@router.post(
    "/upload",
    response_model=KnowledgeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    workspace_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Authorization boundary
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type",
        )

    file_path = UPLOAD_DIR / file.filename

    with open(
        file_path,
        "wb",
    ) as buffer:
        shutil.copyfileobj(
            file.file,
            buffer,
        )

    source = ingestion_service.ingest_document(
        db=db,
        workspace_id=workspace_id,
        file_path=str(file_path),
        original_filename=file.filename,
        title=title,
        file_size=file_path.stat().st_size,
    )

    return {
        "message": "Document uploaded successfully",
        "source": source,
    }


@router.get(
    "",
    response_model=list[KnowledgeListItem],
)
def list_knowledge(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Authorization boundary
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )

    sources = knowledge_service.get_workspace_sources(
        db=db,
        workspace_id=workspace_id,
    )

    return [
        KnowledgeListItem(
            id=source.id,
            workspace_id=source.workspace_id,
            title=source.title,
            filename=source.filename,
            file_type=source.file_type,
            file_size=source.file_size,
            status=source.status,
            created_at=source.created_at,
            updated_at=source.updated_at,
            chunk_count=len(source.chunks),
        )
        for source in sources
    ]


@router.delete(
    "/{source_id}",
)
def delete_document(
    workspace_id: int,
    source_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Authorization boundary
    require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )

    deleted = knowledge_service.delete_source(
        db=db,
        source_id=source_id,
        workspace_id=workspace_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return {
        "message": "Document deleted successfully",
    }