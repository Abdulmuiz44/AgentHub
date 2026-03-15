from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from .base import ProviderAdapter, ProviderCapability
from .ollama import OllamaAdapter
from .openai import OpenAIAdapter


class ProviderConfigurationStatus(StrEnum):
    CONFIGURED = "configured"
    UNCONFIGURED = "unconfigured"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderRegistryEntry:
    capability: ProviderCapability
    adapter: ProviderAdapter
    configuration_status: ProviderConfigurationStatus

    @property
    def is_configured(self) -> bool:
        return self.configuration_status == ProviderConfigurationStatus.CONFIGURED


@dataclass(frozen=True)
class ProviderLookupResult:
    name: str
    entry: ProviderRegistryEntry | None
    configuration_status: ProviderConfigurationStatus

    @property
    def exists(self) -> bool:
        return self.entry is not None

    @property
    def is_configured(self) -> bool:
        return self.configuration_status == ProviderConfigurationStatus.CONFIGURED


def _resolve_configuration_status(provider_name: str) -> ProviderConfigurationStatus:
    if provider_name == "openai":
        api_key = os.getenv("AGENTHUB_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        return ProviderConfigurationStatus.CONFIGURED if api_key else ProviderConfigurationStatus.UNCONFIGURED
    if provider_name == "ollama":
        return ProviderConfigurationStatus.CONFIGURED
    return ProviderConfigurationStatus.UNKNOWN


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderRegistryEntry] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        capability = adapter.capability
        self._providers[capability.name] = ProviderRegistryEntry(
            capability=capability,
            adapter=adapter,
            configuration_status=_resolve_configuration_status(capability.name),
        )

    def list_entries(self) -> list[ProviderRegistryEntry]:
        return list(self._providers.values())

    def list_provider_names(self) -> list[str]:
        return sorted(self._providers.keys())

    def get_entry(self, name: str) -> ProviderRegistryEntry | None:
        return self._providers.get(name)

    def get_by_name(self, name: str) -> ProviderLookupResult:
        entry = self.get_entry(name)
        if entry:
            return ProviderLookupResult(name=name, entry=entry, configuration_status=entry.configuration_status)
        return ProviderLookupResult(name=name, entry=None, configuration_status=ProviderConfigurationStatus.UNKNOWN)

    def get(self, name: str) -> ProviderAdapter | None:
        entry = self.get_entry(name)
        if not entry or not entry.is_configured:
            return None
        return entry.adapter

    def capabilities(self) -> list[ProviderCapability]:
        return [entry.capability for entry in self._providers.values()]

    @classmethod
    def default(cls) -> "ProviderRegistry":
        registry = cls()
        registry.register(OllamaAdapter())
        registry.register(OpenAIAdapter())
        return registry
