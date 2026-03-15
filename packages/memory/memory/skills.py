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
    config_values_json: dict[str, Any] | None = None,
    secret_bindings_json: dict[str, str] | None = None,
    readiness_status: str = "ready",
    readiness_summary: str = "Ready",
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
            config_values_json=config_values_json or {},
            secret_bindings_json=secret_bindings_json or {},
            readiness_status=readiness_status,
            readiness_summary=readiness_summary,
            install_source=install_source,
            created_at=now,
            updated_at=now,
            config_updated_at=now if (config_values_json or secret_bindings_json) else None,
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
        if config_values_json is not None:
            skill.config_values_json = config_values_json
            skill.config_updated_at = now
        if secret_bindings_json is not None:
            skill.secret_bindings_json = secret_bindings_json
            skill.config_updated_at = now
        skill.readiness_status = readiness_status
        skill.readiness_summary = readiness_summary
        skill.updated_at = now
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill_definition(db: DBSession, skill: SkillDefinition, **fields: Any) -> SkillDefinition:
    config_keys = {"config_values_json", "secret_bindings_json"}
    for key, value in fields.items():
        setattr(skill, key, value)
    now = datetime.utcnow()
    if config_keys.intersection(fields):
        skill.config_updated_at = now
    skill.updated_at = now
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill
