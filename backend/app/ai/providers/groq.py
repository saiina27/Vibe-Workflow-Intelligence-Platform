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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
        )


        content = (
            response
            .choices[0]
            .message
            .content
        )


        return AIResponse(
            content=content,
            model=self.model,
            provider="groq",
            input_tokens=0,
            output_tokens=0,
        )