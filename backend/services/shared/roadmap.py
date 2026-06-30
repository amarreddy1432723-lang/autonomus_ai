import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def get_roadmap_manifest() -> dict[str, Any]:
    roadmap_path = Path(__file__).resolve().parents[3] / "roadmap.json"
    with roadmap_path.open("r", encoding="utf-8") as roadmap_file:
        return json.load(roadmap_file)
