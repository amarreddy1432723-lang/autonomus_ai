from __future__ import annotations

from .utils import compact_whitespace, dedupe_preserve_order, stable_hash


class InputNormalizationStage:
    stage_key = "input_normalization"

    def run(self, payload: dict) -> dict:
        source = payload.get("source") or payload
        repository_scopes = source.get("repository_scopes") or []
        normalized = {
            "objective": compact_whitespace(str(source.get("objective") or "")),
            "constraints": list(dedupe_preserve_order(source.get("constraints") or [])),
            "desired_outcomes": list(dedupe_preserve_order(source.get("desired_outcomes") or [])),
            "repository_scopes": repository_scopes,
            "budget": source.get("budget") or {},
        }
        warning_codes: list[str] = []
        if not normalized["repository_scopes"]:
            warning_codes.append("repository_scope_missing")
        if len(normalized["objective"]) < 10:
            warning_codes.append("objective_too_short")
        return {
            "status": "passed" if "objective_too_short" not in warning_codes else "needs_clarification",
            "normalized": normalized,
            "source_hash": stable_hash(normalized),
            "warning_codes": warning_codes,
            "cost_usd": 0.0,
        }
