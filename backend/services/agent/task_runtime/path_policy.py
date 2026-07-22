from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath


RESERVED_ROOTS = {".git", ".hg", ".svn"}
WILDCARD_ROOTS = {"*", "**"}


class PathPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedPath:
    pattern: str
    is_glob: bool = False


def normalize_repository_path(path: str) -> NormalizedPath:
    raw = str(path or "").strip()
    if not raw:
        raise PathPolicyError("Path reservation cannot be empty.")
    if raw.startswith("\\\\"):
        raise PathPolicyError("UNC paths are not allowed in repository reservations.")
    if PureWindowsPath(raw).drive:
        raise PathPolicyError("Absolute or drive-relative paths are not allowed in repository reservations.")
    if raw.startswith("/") or raw.startswith("~"):
        raise PathPolicyError("Absolute paths are not allowed in repository reservations.")

    normalized = raw.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts:
        raise PathPolicyError("Repository root wildcard reservations are not allowed.")
    if any(part == ".." for part in parts):
        raise PathPolicyError("Parent directory traversal is not allowed in repository reservations.")
    if parts[0] in RESERVED_ROOTS:
        raise PathPolicyError("Repository metadata paths cannot be reserved.")
    if parts[0] in WILDCARD_ROOTS:
        raise PathPolicyError("Wildcard repository root reservations are not allowed.")

    clean = "/".join(parts)
    return NormalizedPath(pattern=clean, is_glob=any(char in clean for char in "*?["))


def normalize_repository_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for path in paths:
        clean = normalize_repository_path(path).pattern
        if clean not in normalized:
            normalized.append(clean)
    return normalized


def _literal_prefix(pattern: str) -> str:
    parts = []
    for part in pattern.strip("/").split("/"):
        if any(char in part for char in "*?["):
            break
        parts.append(part)
    return "/".join(parts)


def _parent_child_overlap(left: str, right: str) -> bool:
    left_clean = left.strip("/").lower()
    right_clean = right.strip("/").lower()
    return left_clean == right_clean or left_clean.startswith(f"{right_clean}/") or right_clean.startswith(f"{left_clean}/")


def path_patterns_overlap(left: str, right: str) -> bool:
    left_clean = normalize_repository_path(left).pattern
    right_clean = normalize_repository_path(right).pattern
    if _parent_child_overlap(left_clean, right_clean):
        return True

    left_prefix = _literal_prefix(left_clean)
    right_prefix = _literal_prefix(right_clean)
    if not left_prefix or not right_prefix:
        return True
    return _parent_child_overlap(left_prefix, right_prefix)


def reservation_modes_conflict(existing_mode: str, requested_mode: str) -> bool:
    existing = str(existing_mode or "").lower()
    requested = str(requested_mode or "").lower()
    return not (existing == "read" and requested == "read")
