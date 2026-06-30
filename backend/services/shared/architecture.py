import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def get_system_architecture_manifest() -> dict[str, Any]:
    manifest_path = _repo_root() / "phase2.json"
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


@lru_cache(maxsize=1)
def get_ai_architecture_manifest() -> dict[str, Any]:
    manifest_path = _repo_root() / "phase3.json"
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)
