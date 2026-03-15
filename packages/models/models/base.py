from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

ScalarValue = str | int | float | bool | None


class ProviderCapability(BaseModel):
    name: str
    display_name: str
    models: list[str] = Field(default_factory=list)
    supports_streaming: bool = False


class ProviderMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ProviderGenerationSettings(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False
    stop: list[str] = Field(default_factory=list)


class ProviderGenerationRequest(BaseModel):
    model: str
    messages: list[ProviderMessage]
    settings: ProviderGenerationSettings = Field(default_factory=ProviderGenerationSettings)
    metadata: dict[str, ScalarValue] = Field(default_factory=dict)


class ProviderUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ProviderError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ProviderGenerationResponse(BaseModel):
    provider: str
    model: str
    output_text: str | None = None
    finish_reason: str | None = None
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    metadata: dict[str, ScalarValue] = Field(default_factory=dict)
    error: ProviderError | None = None


class ProviderHealthCheck(BaseModel):
    provider: str
    healthy: bool
    message: str | None = None
    metadata: dict[str, ScalarValue] = Field(default_factory=dict)


class ProviderAdapter(ABC):
    @property
    @abstractmethod
    def capability(self) -> ProviderCapability: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def default_timeout(self) -> float: ...

    @abstractmethod
    def health_check(self) -> ProviderHealthCheck: ...

    @abstractmethod
    def list_models(self) -> list[str]: ...

    @abstractmethod
    def generate(self, request: ProviderGenerationRequest) -> ProviderGenerationResponse: ...
