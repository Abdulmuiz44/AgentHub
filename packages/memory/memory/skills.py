from datetime import datetime
from typing import Any

from sqlmodel import Session as DBSession, select

from .models import SkillDefinition


def get_skill_definition(db: DBSession, name: str) -> SkillDefinition | None:
    statement = select(SkillDefinition).where(SkillDefinition.name == name)
    return db.exec(statement).first()


def list_skill_definitions(db: DBSession) -> list[SkillDefinition]:
    statement = select(SkillDefinition).order_by(SkillDefinition.name)
    return list(db.exec(statement).all())


def upsert_skill_definition(
    db: DBSession,
    *,
    name: str,
    version: str,
    description: str,
    runtime_type: str,
    enabled: bool,
    is_builtin: bool,
    scopes: list[str],
    tags: list[str],
    manifest_json: dict[str, Any],
    install_source: str | None,
) -> SkillDefinition:
    skill = get_skill_definition(db, name)
    now = datetime.utcnow()
    if skill is None:
        skill = SkillDefinition(
            name=name,
            version=version,
            description=description,
            runtime_type=runtime_type,
            enabled=enabled,
            is_builtin=is_builtin,
            scopes=scopes,
            tags=tags,
            manifest_json=manifest_json,
            install_source=install_source,
            created_at=now,
            updated_at=now,
        )
    else:
        skill.version = version
        skill.description = description
        skill.runtime_type = runtime_type
        skill.enabled = enabled
        skill.is_builtin = is_builtin
        skill.scopes = scopes
        skill.tags = tags
        skill.manifest_json = manifest_json
        skill.install_source = install_source
        skill.updated_at = now
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill_definition(db: DBSession, skill: SkillDefinition, **fields: Any) -> SkillDefinition:
    for key, value in fields.items():
        setattr(skill, key, value)
    skill.updated_at = datetime.utcnow()
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill
