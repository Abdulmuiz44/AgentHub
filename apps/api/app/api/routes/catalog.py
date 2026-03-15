from fastapi import APIRouter

from skills.registry import SkillRegistry
from app.config import settings

router = APIRouter(tags=["catalog"])

@router.get("/skills")
def list_skills() -> list[dict[str, object]]:
    return [s.model_dump() for s in SkillRegistry.default(workspace_root=settings.workspace_root).list_manifests()]
