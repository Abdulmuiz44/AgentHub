from .base import ProviderAdapter, ProviderCapability
from .ollama import OllamaAdapter
from .openai import OpenAIAdapter


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        self._providers[adapter.capability.name] = adapter

    def get(self, name: str) -> ProviderAdapter | None:
        return self._providers.get(name)

    def capabilities(self) -> list[ProviderCapability]:
        return [adapter.capability for adapter in self._providers.values()]

    @classmethod
    def default(cls) -> "ProviderRegistry":
        registry = cls()
        registry.register(OllamaAdapter())
        registry.register(OpenAIAdapter())
        return registry
