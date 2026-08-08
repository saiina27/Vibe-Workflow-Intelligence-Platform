import time

from groq import Groq

from app.core.config import settings
from app.schemas.ai import AIRequest, AIResponse


class GroqProvider:

    def __init__(self):

        self.client = Groq(
            api_key=settings.groq_api_key
        )

        self.model = (
            settings.groq_model
            or "llama-3.3-70b-versatile"
        )

    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        start_time = time.time()

        response = self.client.chat.completions.create(
            model=request.model or self.model,
            messages=[
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
        )

        latency = (
            time.time() - start_time
        ) * 1000

        content = (
            response
            .choices[0]
            .message
            .content
        )

        usage = response.usage

        return AIResponse(
            content=content,
            model=request.model or self.model,
            provider="groq",
            input_tokens=(
                usage.prompt_tokens
                if usage
                else 0
            ),
            output_tokens=(
                usage.completion_tokens
                if usage
                else 0
            ),
            latency_ms=latency,
        )