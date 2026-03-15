from .base import ProviderAdapter, ProviderCapability


class OllamaAdapter(ProviderAdapter):
    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name="ollama",
            display_name="Ollama",
            models=["llama3.1", "qwen2.5"],
            supports_streaming=True,
        )

    def generate(self, prompt: str, model: str, **kwargs) -> str:
        _ = (prompt, model, kwargs)
        raise NotImplementedError("Ollama adapter skeleton only")
