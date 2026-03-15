from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession

from app.api.schemas import SkillInstallRequest, SkillResponse, SkillTestResponse
from app.db.session import get_session
from app.services.skills import SkillCatalogService
from skills import SkillManifest

router = APIRouter(tags=["catalog"])


@router.get("/skills", response_model=list[SkillResponse])
def list_skills(db: DBSession = Depends(get_session)) -> list[dict[str, object]]:
    service = SkillCatalogService(db)
    return [service.serialize_skill(skill) for skill in service.list_skills()]


@router.post("/skills/install", response_model=SkillResponse)
def install_skill(payload: SkillInstallRequest, db: DBSession = Depends(get_session)) -> dict[str, object]:
    service = SkillCatalogService(db)
    manifest = SkillManifest.model_validate(payload.manifest.model_dump()) if payload.manifest is not None else None
    try:
        skill = service.install_skill(manifest=manifest, manifest_path=payload.manifest_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.serialize_skill(skill)


@router.get("/skills/{name}", response_model=SkillResponse)
def get_skill(name: str, db: DBSession = Depends(get_session)) -> dict[str, object]:
    service = SkillCatalogService(db)
    skill = service.get_skill(name)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return service.serialize_skill(skill)


@router.post("/skills/{name}/enable", response_model=SkillResponse)
def enable_skill(name: str, db: DBSession = Depends(get_session)) -> dict[str, object]:
    service = SkillCatalogService(db)
    try:
        skill = service.set_enabled(name, True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    return service.serialize_skill(skill)


@router.post("/skills/{name}/disable", response_model=SkillResponse)
def disable_skill(name: str, db: DBSession = Depends(get_session)) -> dict[str, object]:
    service = SkillCatalogService(db)
    try:
        skill = service.set_enabled(name, False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    return service.serialize_skill(skill)


@router.post("/skills/{name}/test", response_model=SkillTestResponse)
def test_skill(name: str, db: DBSession = Depends(get_session)) -> dict[str, object]:
    service = SkillCatalogService(db)
    try:
        skill, result = service.test_skill(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    return {
        "skill": service.serialize_skill(skill),
        "status": result.status.value,
        "summary": result.summary,
        "checked_at": result.checked_at,
        "metadata": result.metadata,
    }
