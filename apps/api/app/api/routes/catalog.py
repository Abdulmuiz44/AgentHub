from fastapi import APIRouter, Query

from app.config import settings
from models.registry import ProviderRegistry
from skills.registry import SkillRegistry

router = APIRouter(tags=["catalog"])


@router.get("/providers")
def list_providers() -> list[dict[str, str | list[str] | bool]]:
    return [p.model_dump() for p in ProviderRegistry.default().capabilities()]


@router.get("/providers/models")
def provider_models(provider: str | None = Query(default=None)) -> list[dict[str, object]]:
    capabilities = ProviderRegistry.default().capabilities()
    if provider:
        capabilities = [item for item in capabilities if item.name == provider]
    return [{"provider": item.name, "models": item.models} for item in capabilities]


@router.get("/providers/health-check")
def provider_health_check() -> list[dict[str, str | bool]]:
    return [
        {
            "provider": "openai",
            "configured": bool(settings.openai_api_key),
            "status": "ready" if settings.openai_api_key else "missing_config",
        },
        {
            "provider": "ollama",
            "configured": bool(settings.ollama_base_url),
            "status": "ready" if settings.ollama_base_url else "missing_config",
        },
    ]


@router.get("/skills")
def list_skills() -> list[dict[str, object]]:
    return [s.model_dump() for s in SkillRegistry.default(workspace_root=settings.workspace_root).list_manifests()]
