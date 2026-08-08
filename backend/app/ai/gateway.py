from app.ai.prompt_cache import PromptCache
from app.ai.router import ProviderRouter
from app.ai.retry import ai_retry
from app.schemas.ai import AIRequest, AIResponse


class AIGateway:

    def __init__(self):

        self.provider = ProviderRouter()

        self.prompt_cache = PromptCache()


    @ai_retry
    def _call_provider(
        self,
        request: AIRequest,
    ) -> AIResponse:

        return self.provider.generate(
            request
        )


    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:


        cached_response = self.prompt_cache.get(
            request.prompt
        )


        if cached_response is not None:

            print("✅ Prompt Cache Hit")

            return AIResponse(
                content=cached_response,
                model="cache",
                provider="cache",
            )


        try:

            ai_response = self._call_provider(
                request
            )


            self.prompt_cache.set(
                prompt=request.prompt,
                response=ai_response.content,
            )


            return ai_response


        except Exception as e:

            print(
                f"AI Gateway Error: {e}"
            )

            raise