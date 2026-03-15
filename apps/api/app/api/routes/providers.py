from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import (
    ProviderHealthCheckRequest,
    ProviderHealthCheckResponse,
    ProviderMetadata,
    ProviderModelsItemResponse,
    ProviderModelsResponse,
    ProviderSummaryResponse,
)
from models.registry import (
    ProviderConfigurationStatus,
    ProviderLookupResult,
    ProviderRegistry,
)

router = APIRouter(tags=["providers"])


def _lookup_provider_or_404(registry: ProviderRegistry, provider_name: str) -> ProviderLookupResult:
    provider = registry.get_by_name(provider_name)
    if not provider.exists:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.get("/providers", response_model=list[ProviderSummaryResponse])
def list_providers() -> list[ProviderSummaryResponse]:
    registry = ProviderRegistry.default()
    return [
        ProviderSummaryResponse(
            provider=ProviderMetadata(**entry.capability.model_dump()),
            configuration_status=entry.configuration_status.value,
            is_configured=entry.is_configured,
        )
        for entry in registry.list_entries()
    ]


@router.get("/providers/models", response_model=ProviderModelsResponse)
def list_provider_models(provider: str | None = Query(default=None)) -> ProviderModelsResponse:
    registry = ProviderRegistry.default()
    if provider:
        selected_provider = _lookup_provider_or_404(registry, provider)
        entries = [selected_provider.entry] if selected_provider.entry else []
    else:
        entries = registry.list_entries()

    providers: list[ProviderModelsItemResponse] = []
    for entry in entries:
        models = entry.capability.models
        adapter = registry.get(entry.capability.name)
        if adapter is not None:
            listed_models = adapter.list_models()
            if listed_models:
                models = listed_models

        providers.append(
            ProviderModelsItemResponse(
                provider_name=entry.capability.name,
                display_name=entry.capability.display_name,
                configuration_status=entry.configuration_status.value,
                is_configured=entry.is_configured,
                models=models,
            )
        )

    return ProviderModelsResponse(providers=providers)


@router.post("/providers/health-check", response_model=ProviderHealthCheckResponse)
def health_check_provider(payload: ProviderHealthCheckRequest) -> ProviderHealthCheckResponse:
    registry = ProviderRegistry.default()
    provider = _lookup_provider_or_404(registry, payload.provider)

    if not provider.is_configured:
        return ProviderHealthCheckResponse(
            provider=payload.provider,
            configuration_status=provider.configuration_status.value,
            healthy=False,
            message="Provider is not configured",
        )

    adapter = registry.get(payload.provider)
    if adapter is None:
        return ProviderHealthCheckResponse(
            provider=payload.provider,
            configuration_status=ProviderConfigurationStatus.UNKNOWN.value,
            healthy=False,
            message="Provider is unavailable",
        )

    health = adapter.health_check()
    return ProviderHealthCheckResponse(
        provider=payload.provider,
        configuration_status=provider.configuration_status.value,
        healthy=health.healthy,
        message=health.message or ("Provider is healthy" if health.healthy else "Provider health check failed"),
    )
