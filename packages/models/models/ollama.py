from __future__ import annotations

import json
import os
from dataclasses import dataclass
from socket import timeout as socket_timeout
from typing import Any
from urllib import error, request

from .base import (
    ProviderAdapter,
    ProviderCapability,
    ProviderError,
    ProviderGenerationRequest,
    ProviderGenerationResponse,
    ProviderHealthCheck,
    ProviderUsage,
)


@dataclass(frozen=True)
class _HttpResult:
    status_code: int
    payload: dict[str, Any]


class OllamaAdapter(ProviderAdapter):
    def __init__(self) -> None:
        self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        timeout_env = os.getenv("OLLAMA_TIMEOUT_SECONDS")
        self._timeout = float(timeout_env) if timeout_env else 30.0

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_timeout(self) -> float:
        return self._timeout

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name=self.provider_name,
            display_name="Ollama",
            models=["llama3.1", "qwen2.5"],
            supports_streaming=True,
        )

    def health_check(self) -> ProviderHealthCheck:
        result = self._request_json("GET", "/api/tags")
        return ProviderHealthCheck(
            provider=self.provider_name,
            healthy=result.status_code < 400,
            message=None if result.status_code < 400 else "Ollama health check failed",
            metadata={"status_code": result.status_code},
        )

    def list_models(self) -> list[str]:
        result = self._request_json("GET", "/api/tags")
        if result.status_code >= 400:
            return []
        models = result.payload.get("models")
        if not isinstance(models, list):
            return []

        model_names = [entry.get("name") for entry in models if isinstance(entry, dict)]
        return [name for name in model_names if isinstance(name, str)]

    def generate(self, request_model: ProviderGenerationRequest) -> ProviderGenerationResponse:
        payload: dict[str, object] = {
            "model": request_model.model,
            "messages": [msg.model_dump() for msg in request_model.messages],
            "stream": request_model.settings.stream,
        }

        options: dict[str, object] = {}
        if request_model.settings.temperature is not None:
            options["temperature"] = request_model.settings.temperature
        if request_model.settings.top_p is not None:
            options["top_p"] = request_model.settings.top_p
        if request_model.settings.max_tokens is not None:
            options["num_predict"] = request_model.settings.max_tokens
        if request_model.settings.stop:
            options["stop"] = request_model.settings.stop
        if options:
            payload["options"] = options

        result = self._request_json("POST", "/api/chat", payload)
        if result.status_code >= 400:
            error_code, retryable = self._normalize_error(result.status_code)
            return self._error_response(
                request_model,
                code=error_code,
                message="Upstream provider request failed",
                retryable=retryable,
                metadata={"status_code": result.status_code},
            )

        message = result.payload.get("message")
        output_text = message.get("content") if isinstance(message, dict) else None
        finish_reason = result.payload.get("done_reason")

        prompt_eval_count = self._int_or_none(result.payload.get("prompt_eval_count"))
        eval_count = self._int_or_none(result.payload.get("eval_count"))
        usage = ProviderUsage(
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            total_tokens=(prompt_eval_count or 0) + (eval_count or 0),
        )

        return ProviderGenerationResponse(
            provider=self.provider_name,
            model=request_model.model,
            output_text=output_text if isinstance(output_text, str) else None,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            usage=usage,
            metadata={"status_code": result.status_code},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> _HttpResult:
        req = request.Request(
            url=f"{self._base_url}{path}",
            method=method,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        )

        try:
            with request.urlopen(req, timeout=self.default_timeout) as response:
                raw = response.read().decode("utf-8")
                response_payload = json.loads(raw) if raw else {}
                if not isinstance(response_payload, dict):
                    return _HttpResult(status_code=598, payload={})
                return _HttpResult(status_code=response.status, payload=response_payload)
        except error.HTTPError as exc:
            return _HttpResult(status_code=exc.code, payload={})
        except (error.URLError, TimeoutError, socket_timeout):
            return _HttpResult(status_code=599, payload={})
        except json.JSONDecodeError:
            return _HttpResult(status_code=598, payload={})

    def _error_response(
        self,
        request_model: ProviderGenerationRequest,
        *,
        code: str,
        message: str,
        retryable: bool,
        metadata: dict[str, int | str | float | bool | None] | None = None,
    ) -> ProviderGenerationResponse:
        return ProviderGenerationResponse(
            provider=self.provider_name,
            model=request_model.model,
            error=ProviderError(code=code, message=message, retryable=retryable),
            metadata=metadata or {},
        )

    def _normalize_error(self, status_code: int) -> tuple[str, bool]:
        if status_code == 404:
            return ("model_not_found", False)
        if status_code == 429:
            return ("rate_limited", True)
        if status_code == 598:
            return ("invalid_response", False)
        if status_code == 599:
            return ("timeout", True)
        if 500 <= status_code:
            return ("provider_unavailable", True)
        return ("provider_error", False)

    def _int_or_none(self, value: object) -> int | None:
        return value if isinstance(value, int) else None
