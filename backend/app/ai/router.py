from app.ai.provider_mapping import get_provider_for_task
from app.schemas.ai import AIRequest, AIResponse
from app.ai.providers.registry import ProviderRegistry
from app.core.config import settings

class ProviderRouter:

    def __init__(self):

        self.registry = ProviderRegistry()

        self.primary = self.registry.get_provider(
            settings.primary_provider
        )

        self.fallback = None

        if settings.fallback_provider:
            self.fallback = self.registry.providers.get(
            settings.fallback_provider
        )


    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        provider_name = get_provider_for_task(
            request.task_type
        )

        provider = self.registry.providers.get(
            provider_name,
            self.primary,
        )

        try:

            return provider.generate(
                request
            )

        except Exception as primary_error:

            print(
                f"{provider_name} failed: {primary_error}"
            )

            if self.fallback:

                print(
                "Switching to fallback provider..."
                )

                return self.fallback.generate(
                request
                )

            raise