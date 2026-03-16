from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from memory.models import SkillDefinition
from skills import SkillConfigField, SkillManifest, SkillReadinessStatus

_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_REDACTION_TOKEN = "[redacted]"


class SkillConfigError(ValueError):
    pass


@dataclass
class SkillConfigSnapshot:
    values: dict[str, Any]
    secret_bindings: dict[str, str]


@dataclass
class ResolvedSkillConfig:
    values: dict[str, Any]
    process_env: dict[str, str]
    readiness_status: SkillReadinessStatus
    readiness_summary: str
    resolved_secret_values: list[str]
    metadata: dict[str, Any]


class SkillConfigService:
    def schema_for_manifest(self, manifest: SkillManifest) -> list[SkillConfigField]:
        return list(manifest.config_fields)

    def snapshot_for_definition(self, definition: SkillDefinition) -> SkillConfigSnapshot:
        return SkillConfigSnapshot(
            values=dict(definition.config_values_json or {}),
            secret_bindings=dict(definition.secret_bindings_json or {}),
        )

    def validate_update(self, manifest: SkillManifest, values: dict[str, Any], secret_bindings: dict[str, str]) -> SkillConfigSnapshot:
        schema = {field.key: field for field in self.schema_for_manifest(manifest)}
        unknown_value_keys = sorted(set(values) - set(schema))
        unknown_binding_keys = sorted(set(secret_bindings) - set(schema))
        if unknown_value_keys or unknown_binding_keys:
            raise SkillConfigError(
                f"Unknown config keys: {', '.join(unknown_value_keys + unknown_binding_keys)}"
            )

        validated_values: dict[str, Any] = {}
        validated_bindings: dict[str, str] = {}
        for field in schema.values():
            if field.secret:
                if field.key in values:
                    raise SkillConfigError(f"Secret field {field.key} must be configured via environment variable binding")
                binding = secret_bindings.get(field.key, "").strip()
                if binding:
                    if not field.env_var_allowed:
                        raise SkillConfigError(f"Field {field.key} does not allow environment variable bindings")
                    if not _ENV_NAME_RE.match(binding):
                        raise SkillConfigError(f"Field {field.key} must use a valid environment variable name")
                    validated_bindings[field.key] = binding
                continue

            if field.key in secret_bindings:
                raise SkillConfigError(f"Field {field.key} is not secret and cannot use an environment binding")

            if field.key in values:
                validated_values[field.key] = self._coerce_value(field, values[field.key])
            elif field.default is not None:
                validated_values[field.key] = field.default

        return SkillConfigSnapshot(values=validated_values, secret_bindings=validated_bindings)

    def evaluate_readiness(self, manifest: SkillManifest, snapshot: SkillConfigSnapshot) -> tuple[SkillReadinessStatus, str]:
        try:
            resolved = self.resolve_runtime_config(manifest, snapshot)
        except SkillConfigError as exc:
            message = str(exc)
            if "environment variable" in message or "binding" in message:
                return SkillReadinessStatus.MISSING_REQUIRED_ENV_BINDING, message
            if "required config" in message:
                return SkillReadinessStatus.MISSING_REQUIRED_CONFIG, message
            return SkillReadinessStatus.INVALID_CONFIG, message
        return resolved.readiness_status, resolved.readiness_summary

    def resolve_runtime_config(self, manifest: SkillManifest, snapshot: SkillConfigSnapshot) -> ResolvedSkillConfig:
        values: dict[str, Any] = {}
        process_env: dict[str, str] = {}
        resolved_secret_values: list[str] = []
        secret_field_status: dict[str, dict[str, Any]] = {}

        for field in self.schema_for_manifest(manifest):
            if field.secret:
                binding = snapshot.secret_bindings.get(field.key, "").strip()
                if field.required and not binding:
                    raise SkillConfigError(f"Missing required environment variable binding for {field.key}")
                if binding:
                    resolved_value = os.environ.get(binding)
                    if resolved_value is None:
                        raise SkillConfigError(f"Missing environment variable value for binding {field.key} -> {binding}")
                    process_env[field.key] = resolved_value
                    resolved_secret_values.append(resolved_value)
                    secret_field_status[field.key] = {"binding": binding, "configured": True}
                else:
                    secret_field_status[field.key] = {"binding": None, "configured": False}
                continue

            if field.key in snapshot.values:
                values[field.key] = self._coerce_value(field, snapshot.values[field.key])
            elif field.default is not None:
                values[field.key] = field.default
            elif field.required:
                raise SkillConfigError(f"Missing required config value for {field.key}")

        if manifest.mcp_stdio is not None:
            for env_key, config_key in manifest.mcp_stdio.env_map.items():
                if config_key in values:
                    process_env[env_key] = str(values[config_key])
                elif config_key in snapshot.secret_bindings:
                    binding = snapshot.secret_bindings[config_key]
                    resolved_value = os.environ.get(binding)
                    if resolved_value is None:
                        raise SkillConfigError(f"Missing environment variable value for binding {config_key} -> {binding}")
                    process_env[env_key] = resolved_value
                    resolved_secret_values.append(resolved_value)
                else:
                    raise SkillConfigError(f"MCP env mapping {env_key} requires configured field {config_key}")

        metadata = {
            "config_readiness": SkillReadinessStatus.READY.value,
            "resolved_env_keys": sorted(process_env.keys()),
            "secret_bindings": secret_field_status,
        }
        return ResolvedSkillConfig(
            values=values,
            process_env=process_env,
            readiness_status=SkillReadinessStatus.READY,
            readiness_summary="Ready",
            resolved_secret_values=resolved_secret_values,
            metadata=metadata,
        )

    def redacted_config_response(self, manifest: SkillManifest, snapshot: SkillConfigSnapshot) -> dict[str, Any]:
        schema = self.schema_for_manifest(manifest)
        readiness_status, readiness_summary = self.evaluate_readiness(manifest, snapshot)
        fields: list[dict[str, Any]] = []
        for field in schema:
            if field.secret:
                binding = snapshot.secret_bindings.get(field.key)
                fields.append(
                    {
                        "key": field.key,
                        "value": None,
                        "configured": bool(binding),
                        "secret_binding": binding,
                        "uses_environment_binding": True,
                    }
                )
            else:
                effective_value = snapshot.values.get(field.key, field.default)
                fields.append(
                    {
                        "key": field.key,
                        "value": effective_value,
                        "configured": effective_value is not None,
                        "secret_binding": None,
                        "uses_environment_binding": False,
                    }
                )
        return {
            "readiness_status": readiness_status.value,
            "readiness_summary": readiness_summary,
            "values": fields,
        }

    def redact_for_display(self, value: Any, secrets: list[str]) -> Any:
        if not secrets:
            return value
        if isinstance(value, str):
            redacted = value
            for secret in secrets:
                if secret:
                    redacted = redacted.replace(secret, _REDACTION_TOKEN)
            return redacted
        if isinstance(value, dict):
            return {key: self.redact_for_display(item, secrets) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_for_display(item, secrets) for item in value]
        return value

    @staticmethod
    def _coerce_value(field: SkillConfigField, value: Any) -> Any:
        if value is None:
            return None
        if field.value_type == "string" or field.value_type == "path":
            return str(value)
        if field.value_type == "integer":
            return int(value)
        if field.value_type == "number":
            return float(value)
        if field.value_type == "boolean":
            if isinstance(value, bool):
                return value
            lowered = str(value).strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
            raise SkillConfigError(f"Field {field.key} requires a boolean value")
        return value
