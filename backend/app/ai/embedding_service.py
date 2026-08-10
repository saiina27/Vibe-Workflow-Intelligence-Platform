
from google import genai

from app.core.config import settings


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768


client = genai.Client(
    api_key=settings.gemini_api_key,
)


class EmbeddingService:

    def generate_embedding(
        self,
        text: str,
    ) -> list[float]:

        if not text or not text.strip():
            raise ValueError(
                "Cannot generate embedding for empty text."
            )

        try:

            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text.strip(),
                config={
                    "output_dimensionality": EMBEDDING_DIMENSION,
                },
            )

            if not response.embeddings:
                raise ValueError(
                    "Embedding API returned no embeddings."
                )

            embedding = response.embeddings[0].values

            if not embedding:
                raise ValueError(
                    "Embedding API returned an empty vector."
                )

            if len(embedding) != EMBEDDING_DIMENSION:
                raise ValueError(
                    "Embedding dimension mismatch: "
                    f"expected {EMBEDDING_DIMENSION}, "
                    f"got {len(embedding)}."
                )

            return embedding

        except Exception as e:

            print(
                f"Embedding generation failed: {e}"
            )

            raise

