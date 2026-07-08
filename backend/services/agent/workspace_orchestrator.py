from __future__ import annotations

import json
from datetime import datetime, timezone


def classify_workspace_modes(prompt: str, selected_mode: str = "auto") -> list[str]:
    text = f"{selected_mode} {prompt}".lower()
    modes: list[str] = []
    if selected_mode and selected_mode != "auto":
        modes.append(selected_mode)
    checks = [
        ("research", ["research", "best practice", "latest", "compare", "find", "search"]),
        ("design", ["design", "ui", "ux", "screen", "page", "component", "layout"]),
        ("deploy", ["deploy", "railway", "vercel", "render", "production", "release"]),
        ("code", ["code", "build", "fix", "bug", "api", "endpoint", "refactor", "test", "implement"]),
    ]
    for mode, keywords in checks:
        if mode not in modes and any(keyword in text for keyword in keywords):
            modes.append(mode)
    return modes or ["code"]


def activity_event(kind: str, message: str, detail: str | None = None) -> dict:
    return {
        "kind": kind,
        "message": message,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def planned_activity(prompt: str, selected_mode: str = "auto") -> list[dict]:
    modes = classify_workspace_modes(prompt, selected_mode)
    events = [activity_event("start", "NEXUS Code orchestrator received prompt", prompt[:180])]
    for mode in modes:
        if mode == "research":
            events.append(activity_event("research", "Research agent queued", "Fetching relevant context only."))
        elif mode == "design":
            events.append(activity_event("design", "Design agent queued", "Preparing interface guidance and implementation handoff."))
        elif mode == "deploy":
            events.append(activity_event("deploy", "Deploy agent queued", "Analyzing deployment configuration without triggering production changes."))
        else:
            events.append(activity_event("code", "Code agent queued", "Reading selected files and preparing implementation plan."))
    events.append(activity_event("done", "Workspace activity plan ready", ", ".join(modes)))
    return events
