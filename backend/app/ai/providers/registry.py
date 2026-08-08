from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.core.config import settings


class ProviderRegistry:

    def __init__(self):

        self.providers = {
            "gemini": GeminiProvider(),
        }

        if settings.groq_api_key:

            self.providers["groq"] = GroqProvider()


    def get_provider(
        self,
        name: str,
    ):

        provider = self.providers.get(name)

        if provider is None:
            raise ValueError(
                f"Provider '{name}' not found"
            )

        return provider