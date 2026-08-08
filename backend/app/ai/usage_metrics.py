from app.schemas.ai import AIResponse


class UsageMetrics:

    def __init__(self):

        self.total_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_latency_ms = 0.0

        self.provider_usage = {}
        self.model_usage = {}

    def record(
        self,
        response: AIResponse,
    ) -> None:

        self.total_requests += 1

        self.total_input_tokens += (
            response.input_tokens
        )

        self.total_output_tokens += (
            response.output_tokens
        )

        self.total_latency_ms += (
            response.latency_ms
        )

        provider = response.provider

        self.provider_usage[provider] = (
            self.provider_usage.get(provider, 0) + 1
        )

        model = response.model

        self.model_usage[model] = (
            self.model_usage.get(model, 0) + 1
        )

    def get_metrics(self) -> dict:

        average_latency = (
            self.total_latency_ms
            / self.total_requests
            if self.total_requests
            else 0.0
        )

        return {
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": (
                self.total_input_tokens
                + self.total_output_tokens
            ),
            "average_latency_ms": average_latency,
            "provider_usage": self.provider_usage,
            "model_usage": self.model_usage,
        }


usage_metrics = UsageMetrics()