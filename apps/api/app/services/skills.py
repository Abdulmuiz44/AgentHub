from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session as DBSession

from app.config import settings
from memory import skills as skill_repo
from memory.models import SkillDefinition
from skills import SkillManifest, SkillRegistry, SkillRuntimeType, SkillTestResult, SkillTestStatus, builtin_manifests


class SkillCatalogService:
    def __init__(self, db: DBSession) -> None:
        self.db = db

    def ensure_catalog_seeded(self) -> None:
        for manifest in builtin_manifests():
            existing = skill_repo.get_skill_definition(self.db, manifest.name)
            enabled = existing.enabled if existing is not None else manifest.enabled_by_default
            skill_repo.upsert_skill_definition(
                self.db,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                runtime_type=manifest.runtime_type.value,
                enabled=enabled,
                is_builtin=True,
                scopes=manifest.scopes,
                tags=sorted(set(manifest.tags + ["builtin"])),
                manifest_json=manifest.model_dump(mode="json"),
                install_source="builtin",
            )

    def list_skills(self) -> list[SkillDefinition]:
        self.ensure_catalog_seeded()
        return skill_repo.list_skill_definitions(self.db)

    def get_skill(self, name: str) -> SkillDefinition | None:
        self.ensure_catalog_seeded()
        return skill_repo.get_skill_definition(self.db, name)

    def install_skill(self, *, manifest: SkillManifest | None = None, manifest_path: str | None = None) -> SkillDefinition:
        self.ensure_catalog_seeded()
        resolved_manifest = manifest or self._load_manifest_from_path(manifest_path)
        if resolved_manifest is None:
            raise ValueError("A manifest payload or manifest_path is required")
        return skill_repo.upsert_skill_definition(
            self.db,
            name=resolved_manifest.name,
            version=resolved_manifest.version,
            description=resolved_manifest.description,
            runtime_type=resolved_manifest.runtime_type.value,
            enabled=resolved_manifest.enabled_by_default,
            is_builtin=False,
            scopes=resolved_manifest.scopes,
            tags=resolved_manifest.tags,
            manifest_json=resolved_manifest.model_dump(mode="json"),
            install_source=resolved_manifest.install_source or manifest_path or "local_manifest",
        )

    def set_enabled(self, name: str, enabled: bool) -> SkillDefinition:
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(name)
        return skill_repo.update_skill_definition(self.db, skill, enabled=enabled)

    def test_skill(self, name: str) -> tuple[SkillDefinition, SkillTestResult]:
        skill_definition = self.get_skill(name)
        if skill_definition is None:
            raise KeyError(name)
        registry = self.build_registry(include_disabled=True)
        skill = registry.get_skill(name)
        if skill is None:
            result = SkillTestResult(status=SkillTestStatus.FAILED, summary="Skill could not be instantiated")
        else:
            result = skill.test()
        skill_definition = skill_repo.update_skill_definition(
            self.db,
            skill_definition,
            last_test_status=result.status.value,
            last_test_summary=result.summary,
            last_tested_at=result.checked_at,
        )
        return skill_definition, result

    def build_registry(self, *, include_disabled: bool = False) -> SkillRegistry:
        manifests: list[SkillManifest] = []
        for definition in self.list_skills():
            if not include_disabled and not definition.enabled:
                continue
            manifests.append(SkillManifest.model_validate(definition.manifest_json))
        return SkillRegistry.from_manifests(
            manifests,
            workspace_root=settings.workspace_root,
            search_provider=settings.search_provider,
            searxng_base_url=settings.searxng_base_url,
        )

    def list_enabled_skill_names(self) -> list[str]:
        return [item.name for item in self.list_skills() if item.enabled]

    @staticmethod
    def serialize_skill(skill: SkillDefinition) -> dict:
        manifest = SkillManifest.model_validate(skill.manifest_json)
        return {
            "id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "runtime_type": skill.runtime_type,
            "enabled": skill.enabled,
            "is_builtin": skill.is_builtin,
            "scopes": list(skill.scopes or []),
            "tags": list(skill.tags or []),
            "install_source": skill.install_source,
            "last_test_status": skill.last_test_status,
            "last_test_summary": skill.last_test_summary,
            "last_tested_at": skill.last_tested_at,
            "manifest": manifest.model_dump(mode="json"),
        }

    @staticmethod
    def _load_manifest_from_path(manifest_path: str | None) -> SkillManifest | None:
        if not manifest_path:
            return None
        target = Path(manifest_path)
        payload = json.loads(target.read_text(encoding="utf-8"))
        return SkillManifest.model_validate(payload)
