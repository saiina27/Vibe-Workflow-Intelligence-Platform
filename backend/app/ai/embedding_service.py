from google import genai

from app.core.config import settings


client = genai.Client(
    api_key=settings.gemini_api_key,
)


class EmbeddingService:

    def generate_embedding(
        self,
        text: str,
    ) -> list[float]:

        try:

            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config={
                    "output_dimensionality": 768
                },
            )

            return response.embeddings[0].values

        except Exception as e:

            print(
                f"Embedding generation error: {e}"
            )

            raise