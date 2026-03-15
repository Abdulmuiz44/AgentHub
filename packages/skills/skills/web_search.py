from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Skill, SkillCapability, SkillManifest, SkillRequest, SkillResult
from .search_provider import (
    SearchProviderError,
    SearchProviderRequest,
    SearchProviderResolver,
    normalize_result_url,
)


class WebSearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float = Field(default=8.0, ge=1.0, le=20.0)


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    rank: int


class WebSearchOutput(BaseModel):
    query: str
    provider: str
    results: list[WebSearchResult] = Field(default_factory=list)


class WebSearchSkill(Skill):
    manifest = SkillManifest(
        name="web_search",
        version="0.1.0",
        description="Search the public web and return normalized ranked results",
        permissions=["net:http"],
        capabilities=[SkillCapability(operation="search_web", read_only=True)],
    )

    def __init__(self, resolver: SearchProviderResolver | None = None) -> None:
        self.resolver = resolver or SearchProviderResolver()

    def execute(self, request: SkillRequest) -> SkillResult:
        try:
            data = WebSearchInput(**request.input)
        except Exception as exc:
            return SkillResult(success=False, error=f"Invalid search input: {exc}")

        if not self._is_standard_query(data.query):
            return SkillResult(success=False, error="Only standard web search queries are supported")

        try:
            provider = self.resolver.resolve()
            response = provider.search(
                SearchProviderRequest(
                    query=data.query,
                    max_results=data.max_results,
                    timeout_seconds=data.timeout_seconds,
                )
            )
        except SearchProviderError as exc:
            return SkillResult(success=False, error=str(exc))

        deduped: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        for item in response.results:
            normalized_url = normalize_result_url(item.url)
            if not normalized_url or normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            deduped.append(
                WebSearchResult(
                    title=item.title.strip()[:240],
                    url=normalized_url,
                    snippet=item.snippet.strip()[:400],
                    rank=len(deduped) + 1,
                )
            )
            if len(deduped) >= data.max_results:
                break

        output = WebSearchOutput(query=data.query, provider=provider.name, results=deduped)
        return SkillResult(
            success=True,
            output=output.model_dump(mode="json"),
            summary=f"Found {len(deduped)} normalized web results for query",
        )

    @staticmethod
    def _is_standard_query(query: str) -> bool:
        lowered = query.lower()
        blocked_markers = ["site:127.0.0.1", "file://", "localhost", "ssh://", "ftp://"]
        return not any(marker in lowered for marker in blocked_markers)
