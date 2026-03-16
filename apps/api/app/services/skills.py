from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session as DBSession

from app.config import settings
from app.services.skill_config import SkillConfigError, SkillConfigService
from core.contracts import PlanningSkillDescriptor
from memory import skills as skill_repo
from memory.models import SkillDefinition
from skills import (
    MCPStdioSkill,
    SkillCapabilityCategory,
    SkillManifest,
    SkillReadinessStatus,
    SkillRegistry,
    SkillTestResult,
    SkillTestStatus,
    UnavailableSkill,
    builtin_manifests,
)
from skills.registry import builtin_skill_factories


class SkillCatalogService:
    def __init__(self, db: DBSession) -> None:
        self.db = db
        self.config_service = SkillConfigService()

    def ensure_catalog_seeded(self) -> None:
        for manifest in builtin_manifests():
            existing = skill_repo.get_skill_definition(self.db, manifest.name)
            enabled = existing.enabled if existing is not None else manifest.enabled_by_default
            snapshot = self.config_service.snapshot_for_definition(existing) if existing is not None else self.config_service.validate_update(manifest, {}, {})
            readiness_status, readiness_summary = self.config_service.evaluate_readiness(manifest, snapshot)
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
                config_values_json=snapshot.values,
                secret_bindings_json=snapshot.secret_bindings,
                readiness_status=readiness_status.value,
                readiness_summary=readiness_summary,
            )

    def list_skills(self) -> list[SkillDefinition]:
        self.ensure_catalog_seeded()
        return [self._refresh_readiness(skill) for skill in skill_repo.list_skill_definitions(self.db)]

    def get_skill(self, name: str) -> SkillDefinition | None:
        self.ensure_catalog_seeded()
        skill = skill_repo.get_skill_definition(self.db, name)
        if skill is None:
            return None
        return self._refresh_readiness(skill)

    def install_skill(self, *, manifest: SkillManifest | None = None, manifest_path: str | None = None) -> SkillDefinition:
        self.ensure_catalog_seeded()
        resolved_manifest = manifest or self._load_manifest_from_path(manifest_path)
        if resolved_manifest is None:
            raise ValueError("A manifest payload or manifest_path is required")
        snapshot = self.config_service.validate_update(resolved_manifest, {}, {})
        readiness_status, readiness_summary = self.config_service.evaluate_readiness(resolved_manifest, snapshot)
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
            config_values_json=snapshot.values,
            secret_bindings_json=snapshot.secret_bindings,
            readiness_status=readiness_status.value,
            readiness_summary=readiness_summary,
        )

    def set_enabled(self, name: str, enabled: bool) -> SkillDefinition:
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(name)
        return skill_repo.update_skill_definition(self.db, skill, enabled=enabled)

    def get_skill_config(self, name: str) -> dict[str, Any]:
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(name)
        manifest = SkillManifest.model_validate(skill.manifest_json)
        snapshot = self.config_service.snapshot_for_definition(skill)
        return {
            "skill_name": skill.name,
            "config_schema": [field.model_dump(mode="json") for field in manifest.config_fields],
            "state": self.config_service.redacted_config_response(manifest, snapshot),
            "updated_at": skill.config_updated_at,
        }

    def update_skill_config(self, name: str, *, values: dict[str, Any], secret_bindings: dict[str, str]) -> SkillDefinition:
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(name)
        manifest = SkillManifest.model_validate(skill.manifest_json)
        snapshot = self.config_service.validate_update(manifest, values, secret_bindings)
        readiness_status, readiness_summary = self.config_service.evaluate_readiness(manifest, snapshot)
        return skill_repo.update_skill_definition(
            self.db,
            skill,
            config_values_json=snapshot.values,
            secret_bindings_json=snapshot.secret_bindings,
            readiness_status=readiness_status.value,
            readiness_summary=readiness_summary,
        )

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
        skill_definition = self._refresh_readiness(skill_definition)
        skill_definition = skill_repo.update_skill_definition(
            self.db,
            skill_definition,
            last_test_status=result.status.value,
            last_test_summary=result.summary,
            last_tested_at=result.checked_at,
        )
        return skill_definition, result

    def build_registry(self, *, include_disabled: bool = False) -> SkillRegistry:
        skills: dict[str, Any] = {}
        native_factories = builtin_skill_factories(
            workspace_root=settings.workspace_root,
            search_provider=settings.search_provider,
            searxng_base_url=settings.searxng_base_url,
        )
        for definition in self.list_skills():
            if not include_disabled and not definition.enabled:
                continue
            manifest = SkillManifest.model_validate(definition.manifest_json)
            snapshot = self.config_service.snapshot_for_definition(definition)
            try:
                resolved = self.config_service.resolve_runtime_config(manifest, snapshot)
            except SkillConfigError as exc:
                skills[definition.name] = UnavailableSkill(
                    manifest,
                    summary=str(exc),
                    readiness_status=SkillReadinessStatus(definition.readiness_status),
                    is_builtin=definition.is_builtin,
                    metadata={
                        "resolved_env_keys": [],
                        "config_readiness": definition.readiness_status,
                        "capability_categories": self._capability_category_values(manifest),
                    },
                )
                continue

            if manifest.runtime_type.value == "native_python":
                factory = native_factories.get(manifest.name)
                if factory is not None:
                    skills[manifest.name] = factory()
                else:
                    skills[manifest.name] = UnavailableSkill(
                        manifest,
                        summary=f"Native skill implementation is unavailable for {manifest.name}",
                        readiness_status=SkillReadinessStatus.INVALID_CONFIG,
                        is_builtin=definition.is_builtin,
                    )
            elif manifest.runtime_type.value == "mcp_stdio":
                skills[manifest.name] = MCPStdioSkill(
                    manifest,
                    is_builtin=definition.is_builtin,
                    runtime_env=resolved.process_env,
                    runtime_metadata={
                        **resolved.metadata,
                        "capability_categories": self._capability_category_values(manifest),
                    },
                    redact_values=resolved.resolved_secret_values,
                )
        return SkillRegistry(skills)

    def list_enabled_skill_names(self) -> list[str]:
        return [item.name for item in self.list_skills() if item.enabled]

    def list_planning_skills(self, *, allowed_names: list[str] | None = None) -> list[PlanningSkillDescriptor]:
        allowed = set(allowed_names or [])
        descriptors: list[PlanningSkillDescriptor] = []
        for skill in self.list_skills():
            if not skill.enabled:
                continue
            if allowed and skill.name not in allowed:
                continue
            manifest = SkillManifest.model_validate(skill.manifest_json)
            categories = self._capability_category_values(manifest)
            if skill.readiness_status != SkillReadinessStatus.READY.value or not categories:
                continue
            approval_required = any(not item.read_only for item in manifest.capabilities)
            descriptors.append(
                PlanningSkillDescriptor(
                    name=skill.name,
                    runtime_type=skill.runtime_type,
                    description=skill.description,
                    scopes=list(skill.scopes or []),
                    capability_categories=categories,
                    readiness=skill.readiness_status,
                    approval_required=approval_required,
                    is_builtin=skill.is_builtin,
                )
            )
        return descriptors

    def serialize_skill(self, skill: SkillDefinition) -> dict[str, Any]:
        skill = self._refresh_readiness(skill)
        manifest = SkillManifest.model_validate(skill.manifest_json)
        snapshot = self.config_service.snapshot_for_definition(skill)
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
            "capability_categories": self._capability_category_values(manifest),
            "install_source": skill.install_source,
            "last_test_status": skill.last_test_status,
            "last_test_summary": skill.last_test_summary,
            "last_tested_at": skill.last_tested_at,
            "readiness_status": skill.readiness_status,
            "readiness_summary": skill.readiness_summary,
            "config_schema": [field.model_dump(mode="json") for field in manifest.config_fields],
            "config_state": self.config_service.redacted_config_response(manifest, snapshot),
            "manifest": manifest.model_dump(mode="json"),
        }

    def _refresh_readiness(self, skill: SkillDefinition) -> SkillDefinition:
        manifest = SkillManifest.model_validate(skill.manifest_json)
        snapshot = self.config_service.snapshot_for_definition(skill)
        readiness_status, readiness_summary = self.config_service.evaluate_readiness(manifest, snapshot)
        if skill.readiness_status == readiness_status.value and skill.readiness_summary == readiness_summary:
            return skill
        return skill_repo.update_skill_definition(
            self.db,
            skill,
            readiness_status=readiness_status.value,
            readiness_summary=readiness_summary,
        )

    @staticmethod
    def _load_manifest_from_path(manifest_path: str | None) -> SkillManifest | None:
        if not manifest_path:
            return None
        target = Path(manifest_path)
        payload = json.loads(target.read_text(encoding="utf-8"))
        return SkillManifest.model_validate(payload)

    @staticmethod
    def _capability_category_values(manifest: SkillManifest) -> list[str]:
        if manifest.capability_categories:
            return [item.value for item in manifest.capability_categories]
        if manifest.capabilities:
            return [SkillCapabilityCategory.CUSTOM_TOOL.value]
        return []
