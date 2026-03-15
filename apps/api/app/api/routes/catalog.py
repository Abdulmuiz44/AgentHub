from fastapi import APIRouter

from models.registry import ProviderRegistry
from skills.registry import SkillRegistry
from app.config import settings

router = APIRouter(tags=["catalog"])


@router.get("/providers")
def list_providers() -> list[dict[str, str | list[str] | bool]]:
    return [p.model_dump() for p in ProviderRegistry.default().capabilities()]


@router.get("/skills")
def list_skills() -> list[dict[str, object]]:
    return [s.model_dump() for s in SkillRegistry.default(workspace_root=settings.workspace_root).list_manifests()]
