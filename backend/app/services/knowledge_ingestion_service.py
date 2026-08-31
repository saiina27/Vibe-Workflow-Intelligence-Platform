
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.embedding_service import EmbeddingService
from app.ai.text_chunker import TextChunker
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeStatus,
)
from app.repositories.knowledge_chunk_repository import (
    KnowledgeChunkRepository,
)
from app.repositories.knowledge_repository import (
    KnowledgeRepository,
)
from app.services.document_loader import (
    DocumentLoader,
)


class KnowledgeIngestionService:

    def __init__(self):
        self.loader = DocumentLoader()
        self.chunker = TextChunker()
        self.embedding_service = EmbeddingService()
        self.repository = KnowledgeRepository()
        self.chunk_repository = KnowledgeChunkRepository()

    def ingest_document(
        self,
        db: Session,
        workspace_id: int,
        file_path: str,
        original_filename: str,
        title: str,
        file_size: int,
    ) -> KnowledgeSource:

        source = KnowledgeSource(
            workspace_id=workspace_id,
            title=title,
            filename=original_filename,
            file_type=Path(
                original_filename
            ).suffix.lower(),
            file_size=file_size,
            status=KnowledgeStatus.PROCESSING,
        )

        source = self.repository.create_source(
            db=db,
            source=source,
        )

        try:

            # -------------------------
            # Load Document
            # -------------------------

            text = self.loader.load(
                file_path=file_path,
            )

            if not text or not text.strip():
                raise ValueError(
                    "Document contains no readable text."
                )

            # -------------------------
            # Create Chunks
            # -------------------------

            chunks = self.chunker.chunk(
                text=text,
            )

            if not chunks:
                raise ValueError(
                    "Document produced no chunks."
                )

            print("=" * 60)
            print("RAG INGESTION")
            print(f"Source ID: {source.id}")
            print(f"Filename: {original_filename}")
            print(f"Text Length: {len(text)}")
            print(f"Total Chunks: {len(chunks)}")
            print("=" * 60)

            # -------------------------
            # Generate Embeddings
            # -------------------------

            chunk_models: list[KnowledgeChunk] = []

            for index, chunk_text in enumerate(chunks):

                if not chunk_text or not chunk_text.strip():
                    continue

                embedding = (
                    self.embedding_service.generate_embedding(
                        chunk_text
                    )
                )

                chunk_models.append(
                    KnowledgeChunk(
                        knowledge_source_id=source.id,
                        workspace_id=workspace_id,
                        chunk_index=index,
                        text=chunk_text,
                        embedding=embedding,
                        chunk_metadata={
                            "source": original_filename,
                            "chunk": index,
                        },
                    )
                )

            if not chunk_models:
                raise ValueError(
                    "No valid knowledge chunks were created."
                )

            # -------------------------
            # Persist Chunks
            # -------------------------

            self.chunk_repository.create_many(
                db=db,
                chunks=chunk_models,
            )

            # -------------------------
            # Mark Source Ready
            # -------------------------

            self.repository.update_status(
                db=db,
                source=source,
                status=KnowledgeStatus.READY,
            )

            print(
                f"RAG ingestion completed: "
                f"{len(chunk_models)} chunks stored."
            )

            return source

        except Exception as e:

            print(
                f"RAG ingestion failed for "
                f"source {source.id}: {e}"
            )

            self.repository.update_status(
                db=db,
                source=source,
                status=KnowledgeStatus.FAILED,
            )

            raise

