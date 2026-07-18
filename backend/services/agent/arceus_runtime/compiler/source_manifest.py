from __future__ import annotations

import uuid

from .utils import stable_hash


class SourceManifestStage:
    stage_key = "source_manifest"

    def run(self, payload: dict) -> dict:
        source = payload["source"]
        repositories = source.get("repository_scopes") or []
        manifest = {
            "project_id": source.get("project_id"),
            "mission_id": source.get("mission_id"),
            "source_mission_version": source.get("source_mission_version"),
            "repositories": [
                {
                    "repository_id": item.get("repository_id"),
                    "provider": item.get("provider"),
                    "repository_url": item.get("repository_url"),
                    "base_ref": item.get("base_ref"),
                    "allowed_paths": item.get("allowed_paths") or [],
                    "denied_paths": item.get("denied_paths") or [],
                }
                for item in repositories
            ],
            "workspace_constraints": {
                "repository_count": len(repositories),
                "path_scoped": any(item.get("allowed_paths") for item in repositories),
                "has_denied_paths": any(item.get("denied_paths") for item in repositories),
            },
        }
        manifest_hash = stable_hash(manifest)
        return {
            "status": "passed",
            "source_manifest_id": str(uuid.uuid5(uuid.NAMESPACE_URL, manifest_hash)),
            "source_manifest": manifest,
            "source_manifest_hash": manifest_hash,
            "warning_codes": [] if repositories else ["repository_scope_missing"],
            "cost_usd": 0.0001,
        }

