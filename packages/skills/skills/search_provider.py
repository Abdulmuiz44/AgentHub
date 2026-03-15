from __future__ import annotations

import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str = ""
    rank: int


class SearchProviderRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float = Field(default=8.0, ge=1.0, le=20.0)


class SearchProviderResponse(BaseModel):
    query: str
    results: list[SearchResultItem] = Field(default_factory=list)


class SearchProviderError(RuntimeError):
    pass


class SearchProvider:
    name: str

    def search(self, request: SearchProviderRequest) -> SearchProviderResponse:
        raise NotImplementedError


class SearxngSearchProvider(SearchProvider):
    name = "searxng"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def search(self, request: SearchProviderRequest) -> SearchProviderResponse:
        query = urlencode({"q": request.query, "format": "json", "language": "en"})
        endpoint = f"{self.base_url}/search?{query}"
        req = Request(endpoint, headers={"User-Agent": "AgentHubSearchSkill/0.1"})
        try:
            with urlopen(req, timeout=request.timeout_seconds) as response:  # noqa: S310
                payload = response.read(1_000_000)
        except OSError as exc:
            raise SearchProviderError(f"search provider request failed: {exc}") from exc

        try:
            data = json.loads(payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise SearchProviderError("search provider returned invalid JSON") from exc

        normalized: list[SearchResultItem] = []
        for raw in data.get("results", []):
            title = str(raw.get("title", "")).strip()
            url = str(raw.get("url", "")).strip()
            snippet = str(raw.get("content", "")).strip()
            if not title or not url:
                continue
            normalized.append(SearchResultItem(title=title, url=url, snippet=snippet, rank=len(normalized) + 1))
            if len(normalized) >= request.max_results:
                break

        return SearchProviderResponse(query=request.query, results=normalized)


class DuckDuckGoInstantSearchProvider(SearchProvider):
    name = "duckduckgo_instant"

    def search(self, request: SearchProviderRequest) -> SearchProviderResponse:
        query = urlencode({"q": request.query, "format": "json", "no_redirect": "1", "no_html": "1"})
        req = Request(f"https://api.duckduckgo.com/?{query}", headers={"User-Agent": "AgentHubSearchSkill/0.1"})
        try:
            with urlopen(req, timeout=request.timeout_seconds) as response:  # noqa: S310
                payload = response.read(1_000_000)
        except OSError as exc:
            raise SearchProviderError(f"search provider request failed: {exc}") from exc

        try:
            data = json.loads(payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise SearchProviderError("search provider returned invalid JSON") from exc

        results: list[SearchResultItem] = []

        def consume_topic(topic: dict) -> None:
            url = str(topic.get("FirstURL", "")).strip()
            text = str(topic.get("Text", "")).strip()
            if not url:
                return
            title = text.split(" - ")[0].strip() if text else url
            results.append(SearchResultItem(title=title or url, url=url, snippet=text, rank=len(results) + 1))

        for item in data.get("RelatedTopics", []):
            if isinstance(item, dict) and "Topics" in item:
                for nested in item.get("Topics", []):
                    if isinstance(nested, dict):
                        consume_topic(nested)
            elif isinstance(item, dict):
                consume_topic(item)
            if len(results) >= request.max_results:
                break

        if not results and data.get("AbstractURL"):
            title = str(data.get("Heading") or request.query).strip()
            results.append(
                SearchResultItem(
                    title=title,
                    url=str(data.get("AbstractURL")),
                    snippet=str(data.get("AbstractText", "")).strip(),
                    rank=1,
                )
            )

        return SearchProviderResponse(query=request.query, results=results[: request.max_results])


@dataclass
class SearchProviderResolverConfig:
    explicit_provider: str | None = None
    searxng_base_url: str | None = None


class SearchProviderResolver:
    def __init__(self, config: SearchProviderResolverConfig | None = None) -> None:
        resolved = config or SearchProviderResolverConfig(
            explicit_provider=os.getenv("AGENTHUB_SEARCH_PROVIDER"),
            searxng_base_url=os.getenv("AGENTHUB_SEARXNG_BASE_URL"),
        )
        self.config = resolved

    def resolve(self) -> SearchProvider:
        provider_name = (self.config.explicit_provider or "").strip().lower()
        searxng_url = (self.config.searxng_base_url or "").strip()

        if provider_name == "searxng" and not searxng_url:
            raise SearchProviderError("AGENTHUB_SEARCH_PROVIDER=searxng requires AGENTHUB_SEARXNG_BASE_URL")

        if searxng_url and provider_name in {"", "searxng"}:
            return SearxngSearchProvider(searxng_url)

        if provider_name in {"", "duckduckgo", "duckduckgo_instant"}:
            return DuckDuckGoInstantSearchProvider()

        raise SearchProviderError(f"unsupported search provider: {provider_name}")


def normalize_result_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None

    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return None

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        infos = []

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return None

    cleaned_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=False)))
    normalized = parsed._replace(fragment="", query=cleaned_query)
    return urlunparse(normalized)
