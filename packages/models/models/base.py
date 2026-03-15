from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ProviderCapability(BaseModel):
    name: str
    display_name: str
    models: list[str] = Field(default_factory=list)
    supports_streaming: bool = False


class ProviderAdapter(ABC):
    @property
    @abstractmethod
    def capability(self) -> ProviderCapability: ...

    @abstractmethod
    def generate(self, prompt: str, model: str, **kwargs: Any) -> str: ...
