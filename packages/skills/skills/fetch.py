from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import Skill, SkillCapability, SkillManifest, SkillRequest, SkillResult, SkillRuntimeType, SkillTestResult, SkillTestStatus


class FetchValidationError(ValueError):
    pass


class FetchConfig:
    def __init__(self, timeout_seconds: float = 8.0, max_content_bytes: int = 200_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_content_bytes = max_content_bytes


class FetchSkill(Skill):
    manifest = SkillManifest(
        name="fetch",
        version="0.1.0",
        description="Fetch remote HTTP/HTTPS text content",
        runtime_type=SkillRuntimeType.NATIVE_PYTHON,
        scopes=["network:read"],
        permissions=["net:http"],
        tags=["builtin", "http", "research"],
        input_schema_summary={"url": "HTTP or HTTPS URL to fetch"},
        output_schema_summary={"metadata": "fetch metadata", "text": "UTF-8 response preview"},
        capabilities=[SkillCapability(operation="fetch_url", read_only=True, description="Fetch a remote URL")],
    )

    def __init__(self, config: FetchConfig | None = None) -> None:
        self.config = config or FetchConfig()

    def execute(self, request: SkillRequest) -> SkillResult:
        url = str(request.input.get("url", "")).strip()
        try:
            metadata, text = self.fetch_url(url)
            return SkillResult(
                success=True,
                output={"metadata": metadata, "text": text},
                summary=f"Fetched {metadata['url']}",
                runtime_type=self.manifest.runtime_type,
                skill_name=self.manifest.name,
                metadata={"builtin": True},
            )
        except FetchValidationError as exc:
            return SkillResult(
                success=False,
                error=str(exc),
                runtime_type=self.manifest.runtime_type,
                skill_name=self.manifest.name,
                metadata={"builtin": True},
            )

    def test(self) -> SkillTestResult:
        return SkillTestResult(status=SkillTestStatus.PASSED, summary="Fetch skill configuration is available")

    def fetch_url(self, url: str) -> tuple[dict[str, str | int | bool], str]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise FetchValidationError("Only http and https URLs are supported")
        if not parsed.hostname:
            raise FetchValidationError("URL host is required")
        self._guard_host(parsed.hostname)

        request = Request(url, headers={"User-Agent": "AgentHubFetchSkill/0.1"})
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                content_type = response.headers.get("Content-Type", "")
                status = int(getattr(response, "status", 200))
                payload = response.read(self.config.max_content_bytes + 1)
        except TimeoutError as exc:
            raise FetchValidationError("Request timed out") from exc
        except OSError as exc:
            raise FetchValidationError(f"Network error: {exc}") from exc

        truncated = len(payload) > self.config.max_content_bytes
        payload = payload[: self.config.max_content_bytes]

        try:
            text = payload.decode("utf-8", errors="replace")
        except Exception as exc:
            raise FetchValidationError(f"Unable to decode response body: {exc}") from exc

        if not text.strip() and "text" not in content_type.lower():
            raise FetchValidationError("Response does not contain readable text")

        metadata = {
            "url": url,
            "status_code": status,
            "content_type": content_type,
            "content_length": len(payload),
            "truncated": truncated,
        }
        return metadata, text

    @staticmethod
    def _guard_host(host: str) -> None:
        if host in {"localhost", "127.0.0.1", "::1"}:
            raise FetchValidationError("Localhost targets are not allowed")

        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise FetchValidationError(f"Unable to resolve host: {host}") from exc

        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise FetchValidationError("Private or local network targets are not allowed")
