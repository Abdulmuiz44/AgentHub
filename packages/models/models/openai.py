from .base import ProviderAdapter, ProviderCapability


class OpenAIAdapter(ProviderAdapter):
    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name="openai",
            display_name="OpenAI",
            models=["gpt-4o-mini", "gpt-4.1-mini"],
            supports_streaming=True,
        )

    def generate(self, prompt: str, model: str, **kwargs) -> str:
        _ = (prompt, model, kwargs)
        raise NotImplementedError("OpenAI adapter skeleton only")
