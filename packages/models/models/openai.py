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
    headers: dict[str, str]


class OpenAIAdapter(ProviderAdapter):
    def __init__(self) -> None:
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self._base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        timeout_env = os.getenv("OPENAI_TIMEOUT_SECONDS")
        self._timeout = float(timeout_env) if timeout_env else 30.0

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def default_timeout(self) -> float:
        return self._timeout

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name=self.provider_name,
            display_name="OpenAI",
            models=["gpt-4o-mini", "gpt-4.1-mini"],
            supports_streaming=True,
        )

    def health_check(self) -> ProviderHealthCheck:
        if not self._api_key:
            return ProviderHealthCheck(
                provider=self.provider_name,
                healthy=False,
                message="OPENAI_API_KEY is not configured",
            )

        result = self._request_json("GET", "/models")
        return ProviderHealthCheck(
            provider=self.provider_name,
            healthy=result.status_code < 400,
            message=None if result.status_code < 400 else "OpenAI health check failed",
            metadata={"status_code": result.status_code},
        )

    def list_models(self) -> list[str]:
        if not self._api_key:
            return []

        result = self._request_json("GET", "/models")
        if result.status_code >= 400:
            return []

        data = result.payload.get("data")
        if not isinstance(data, list):
            return []

        model_ids = [entry.get("id") for entry in data if isinstance(entry, dict)]
        return [model_id for model_id in model_ids if isinstance(model_id, str)]

    def generate(self, request_model: ProviderGenerationRequest) -> ProviderGenerationResponse:
        if not self._api_key:
            return self._error_response(
                request_model,
                code="auth_missing",
                message="Provider credentials are not configured",
                retryable=False,
            )

        payload: dict[str, object] = {
            "model": request_model.model,
            "messages": [msg.model_dump() for msg in request_model.messages],
            "stream": request_model.settings.stream,
        }
        if request_model.settings.temperature is not None:
            payload["temperature"] = request_model.settings.temperature
        if request_model.settings.max_tokens is not None:
            payload["max_tokens"] = request_model.settings.max_tokens
        if request_model.settings.top_p is not None:
            payload["top_p"] = request_model.settings.top_p
        if request_model.settings.stop:
            payload["stop"] = request_model.settings.stop

        result = self._request_json("POST", "/chat/completions", payload)
        if result.status_code >= 400:
            error_code, retryable = self._normalize_error(result.status_code)
            return self._error_response(
                request_model,
                code=error_code,
                message="Upstream provider request failed",
                retryable=retryable,
                metadata={"status_code": result.status_code},
            )

        choices = result.payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._error_response(
                request_model,
                code="invalid_response",
                message="Provider returned an unexpected response format",
                retryable=False,
                metadata={"status_code": result.status_code},
            )

        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        output_text = message.get("content") if isinstance(message, dict) else None
        finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None

        usage_payload = result.payload.get("usage")
        usage = ProviderUsage(
            input_tokens=self._int_or_none(usage_payload.get("prompt_tokens")) if isinstance(usage_payload, dict) else None,
            output_tokens=self._int_or_none(usage_payload.get("completion_tokens")) if isinstance(usage_payload, dict) else None,
            total_tokens=self._int_or_none(usage_payload.get("total_tokens")) if isinstance(usage_payload, dict) else None,
        )

        response_metadata: dict[str, int | str | float | bool | None] = {
            "status_code": result.status_code,
            "request_id": result.headers.get("x-request-id"),
        }
        if request_model.metadata:
            response_metadata["metadata_keys"] = ",".join(sorted(request_model.metadata.keys()))

        return ProviderGenerationResponse(
            provider=self.provider_name,
            model=request_model.model,
            output_text=output_text if isinstance(output_text, str) else None,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            usage=usage,
            metadata=response_metadata,
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
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        )
        try:
            with request.urlopen(req, timeout=self.default_timeout) as response:
                raw = response.read().decode("utf-8")
                response_payload = json.loads(raw) if raw else {}
                if not isinstance(response_payload, dict):
                    return _HttpResult(status_code=598, payload={}, headers={})
                headers = {key.lower(): value for key, value in response.headers.items()}
                return _HttpResult(status_code=response.status, payload=response_payload, headers=headers)
        except error.HTTPError as exc:
            return _HttpResult(status_code=exc.code, payload={}, headers={})
        except (error.URLError, TimeoutError, socket_timeout):
            return _HttpResult(status_code=599, payload={}, headers={})
        except json.JSONDecodeError:
            return _HttpResult(status_code=598, payload={}, headers={})

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
        if status_code == 401:
            return ("auth_error", False)
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
