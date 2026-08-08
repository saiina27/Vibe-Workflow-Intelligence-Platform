import time

from google import genai

from app.ai.providers.base import AIProvider
from app.core.config import settings
from app.schemas.ai import AIRequest, AIResponse


class GeminiProvider(AIProvider):

    def __init__(self):

        self.client = genai.Client(
            api_key=settings.gemini_api_key
        )


    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        start_time = time.time()


        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=request.prompt,
        )


        latency = (
            time.time() - start_time
        ) * 1000


        return AIResponse(

            content=response.text,

            model=settings.gemini_model,

            provider="gemini",

            latency_ms=latency,

        )