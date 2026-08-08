from app.ai.providers.registry import ProviderRegistry
from app.ai.routing_decision import build_routing_decision
from app.schemas.ai import AIRequest, AIResponse
from app.core.config import settings


class ProviderRouter:

    def __init__(self):

        self.registry = ProviderRegistry()

        self.primary = self.registry.get_provider(
            settings.primary_provider
        )

        self.fallback = None

        if settings.fallback_provider:

            self.fallback = (
                self.registry.providers.get(
                    settings.fallback_provider
                )
            )

    def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:

        decision = build_routing_decision(
            request.task_type,
            request.complexity,
        )

        provider = self.registry.providers.get(
            decision.provider,
            self.primary,
        )

        request.model = decision.model

        print("=" * 60)
        print("AI ROUTING DECISION")
        print(f"Task: {decision.task_type.value}")
        print(f"Complexity: {decision.complexity.value}")
        print(f"Provider: {decision.provider}")
        print(f"Model: {decision.model}")
        print(f"Reason: {decision.reason}")
        print("=" * 60)

        try:

            return provider.generate(
                request
            )

        except Exception as primary_error:

            print(
                f"{decision.provider} failed: "
                f"{primary_error}"
            )

            if self.fallback:

                print(
                    "Switching to fallback provider..."
                )

                return self.fallback.generate(
                    request
                )

            raise