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
            model=request.model or settings.gemini_model,
            contents=request.prompt,
        )


        latency = (
            time.time() - start_time
        ) * 1000


        usage = response.usage_metadata

        return AIResponse(

            content=response.text,

            model=request.model or settings.gemini_model,

            provider="gemini",

            input_tokens=(
                usage.prompt_token_count
                if usage
                else 0
            ),

            output_tokens=(
                usage.candidates_token_count
                if usage
                else 0
            ),

            latency_ms=latency,

        )