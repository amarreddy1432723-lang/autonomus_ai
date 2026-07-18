from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.]{12,}", re.IGNORECASE),
    re.compile(r"(password|token|secret)=\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(RSA\s+|OPENSSH\s+)?PRIVATE KEY-----"),
]


@dataclass(frozen=True)
class ValidationResult:
    status: str
    normalized_output: dict[str, Any] | str | list[Any]
    errors: list[str]
    quarantined: bool = False


def scan_output_for_sensitive_material(value: Any) -> list[str]:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    findings = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append("sensitive_material_detected")
    return sorted(set(findings))


def _validate_object_schema(output: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(output, dict):
        return ["schema_type_object_expected"]
    if schema.get("type") == "array" and not isinstance(output, list):
        return ["schema_type_array_expected"]
    if isinstance(output, dict):
        for key in schema.get("required", []):
            if key not in output:
                errors.append(f"required_property_missing:{key}")
        properties = schema.get("properties") or {}
        for key, spec in properties.items():
            if key not in output:
                continue
            expected_type = spec.get("type")
            value = output[key]
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"property_type_mismatch:{key}:string")
            elif expected_type == "number" and not isinstance(value, int | float):
                errors.append(f"property_type_mismatch:{key}:number")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"property_type_mismatch:{key}:integer")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"property_type_mismatch:{key}:boolean")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"property_type_mismatch:{key}:array")
            elif expected_type == "object" and not isinstance(value, dict):
                errors.append(f"property_type_mismatch:{key}:object")
    return errors


def validate_model_output(raw_output: Any, schema: dict[str, Any] | None) -> ValidationResult:
    normalized = raw_output
    errors: list[str] = []
    if schema:
        if isinstance(raw_output, str):
            try:
                normalized = json.loads(raw_output)
            except json.JSONDecodeError:
                errors.append("json_parse_failed")
        if not errors:
            errors.extend(_validate_object_schema(normalized, schema))
    findings = scan_output_for_sensitive_material(normalized)
    errors.extend(findings)
    quarantined = bool(findings)
    status = "quarantined" if quarantined else "valid" if not errors else "invalid"
    return ValidationResult(status=status, normalized_output=normalized, errors=errors, quarantined=quarantined)

