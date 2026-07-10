from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


PermissionLevel = Literal["automatic", "confirm_once", "always_confirm", "prohibited"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    category: str
    permission: PermissionLevel
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    tags: tuple[str, ...] = field(default_factory=tuple)
    requires_workspace: bool = False
    enabled: bool = True

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "permission": self.permission,
            "risk_level": self.risk_level,
            "input_schema": self.input_schema,
            "tags": list(self.tags),
            "requires_workspace": self.requires_workspace,
            "enabled": self.enabled,
        }

    def llm_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOLS: tuple[AgentTool, ...] = (
    AgentTool(
        name="list_files",
        description="List the files and folders available in the current workspace.",
        category="coding",
        permission="automatic",
        risk_level="low",
        requires_workspace=True,
        tags=("code", "files", "workspace", "explore"),
        input_schema=_schema({"session_id": {"type": "string"}}),
    ),
    AgentTool(
        name="read_file",
        description="Read the contents of an approved workspace or uploaded file.",
        category="coding",
        permission="automatic",
        risk_level="low",
        requires_workspace=True,
        tags=("code", "files", "context"),
        input_schema=_schema(
            {
                "file_id": {"type": "string"},
                "path": {"type": "string", "description": "Optional workspace-relative path."},
            }
        ),
    ),
    AgentTool(
        name="search_code",
        description="Search workspace files, symbols, imports, and text snippets.",
        category="coding",
        permission="automatic",
        risk_level="low",
        requires_workspace=True,
        tags=("code", "search", "symbols", "debug"),
        input_schema=_schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["query"],
        ),
    ),
    AgentTool(
        name="analyze_workspace",
        description="Analyze project structure, languages, dependencies, routes, and likely checks.",
        category="coding",
        permission="automatic",
        risk_level="low",
        requires_workspace=True,
        tags=("code", "analysis", "dependencies", "routes"),
        input_schema=_schema({"session_id": {"type": "string"}}),
    ),
    AgentTool(
        name="apply_patch",
        description="Prepare or apply approved source-code changes as a reviewable patch.",
        category="coding",
        permission="confirm_once",
        risk_level="medium",
        requires_workspace=True,
        tags=("code", "edit", "patch", "diff"),
        input_schema=_schema(
            {
                "instruction": {"type": "string"},
                "approved": {"type": "boolean"},
            },
            ["instruction"],
        ),
    ),
    AgentTool(
        name="run_tests",
        description="Run discovered project test/build/lint/typecheck commands through workspace policy.",
        category="coding",
        permission="automatic",
        risk_level="medium",
        requires_workspace=True,
        tags=("code", "tests", "checks", "build"),
        input_schema=_schema(
            {
                "commands": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 300},
            }
        ),
    ),
    AgentTool(
        name="run_command",
        description="Execute an approved terminal command inside the workspace sandbox.",
        category="coding",
        permission="confirm_once",
        risk_level="high",
        requires_workspace=True,
        tags=("code", "terminal", "sandbox", "cli"),
        input_schema=_schema(
            {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 900},
                "approved": {"type": "boolean"},
            },
            ["command"],
        ),
    ),
    AgentTool(
        name="git_diff",
        description="Inspect pending workspace changes and approved patch previews.",
        category="coding",
        permission="automatic",
        risk_level="low",
        requires_workspace=True,
        tags=("code", "git", "diff", "review"),
        input_schema=_schema({"session_id": {"type": "string"}}),
    ),
    AgentTool(
        name="github_pr",
        description="Create branches, commits, and pull requests using the connected GitHub App.",
        category="coding",
        permission="always_confirm",
        risk_level="high",
        requires_workspace=True,
        tags=("code", "github", "pr", "git"),
        input_schema=_schema(
            {
                "action": {"type": "string", "enum": ["import", "branch", "commit", "pr", "status"]},
                "repository": {"type": "string"},
                "branch": {"type": "string"},
                "message": {"type": "string"},
            },
            ["action"],
        ),
    ),
    AgentTool(
        name="preview_check",
        description="Open a workspace preview, capture screenshot/log evidence, and summarize UI/runtime failures.",
        category="coding",
        permission="automatic",
        risk_level="medium",
        requires_workspace=True,
        tags=("code", "browser", "preview", "visual"),
        input_schema=_schema({"url": {"type": "string"}}),
    ),
    AgentTool(
        name="rollback_changes",
        description="Rollback the last applied workspace patch or a selected checkpoint.",
        category="coding",
        permission="always_confirm",
        risk_level="high",
        requires_workspace=True,
        tags=("code", "rollback", "checkpoint", "safety"),
        input_schema=_schema({"snapshot_id": {"type": "string"}}),
    ),
    AgentTool(
        name="web_search",
        description="Search the web for current information, documentation, media, jobs, or company research.",
        category="research",
        permission="automatic",
        risk_level="low",
        tags=("research", "web", "news", "docs", "company"),
        input_schema=_schema({"query": {"type": "string"}}, ["query"]),
    ),
    AgentTool(
        name="memory_search",
        description="Retrieve relevant saved memories and user-approved context.",
        category="memory",
        permission="automatic",
        risk_level="low",
        tags=("memory", "context", "personalization"),
        input_schema=_schema({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    ),
    AgentTool(
        name="calendar_create",
        description="Create or update a calendar event through a connected PA calendar app.",
        category="personal_assistant",
        permission="always_confirm",
        risk_level="high",
        tags=("pa", "calendar", "schedule"),
        input_schema=_schema(
            {
                "title": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
            },
            ["title", "start"],
        ),
    ),
    AgentTool(
        name="email_draft",
        description="Draft an email through a connected PA email app. Sending always requires confirmation.",
        category="personal_assistant",
        permission="always_confirm",
        risk_level="high",
        tags=("pa", "email", "draft"),
        input_schema=_schema(
            {
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            ["subject", "body"],
        ),
    ),
)


TOOL_REGISTRY: dict[str, AgentTool] = {tool.name: tool for tool in TOOLS}


INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "software_debugging": ("bug", "error", "failing", "fix", "debug", "test", "traceback", "exception", "not working"),
    "software_implementation": ("implement", "build", "add", "create", "refactor", "endpoint", "component", "feature"),
    "software_review": ("review", "diff", "changes", "rollback", "pr", "pull request", "commit"),
    "software_preview": ("preview", "screenshot", "browser", "ui broken", "console", "network", "blank page"),
    "research": ("research", "latest", "compare", "find", "search", "docs", "news", "company"),
    "personal_productivity": ("schedule", "calendar", "email", "meeting", "remind", "task", "daily brief"),
    "interview": ("interview", "resume", "candidate", "question", "answer", "company prep"),
}


INTENT_TOOLS: dict[str, tuple[str, ...]] = {
    "software_debugging": ("search_code", "read_file", "analyze_workspace", "run_tests", "run_command", "git_diff", "apply_patch"),
    "software_implementation": ("list_files", "search_code", "read_file", "analyze_workspace", "apply_patch", "run_tests", "git_diff"),
    "software_review": ("git_diff", "read_file", "run_tests", "github_pr", "rollback_changes"),
    "software_preview": ("preview_check", "read_file", "search_code", "apply_patch", "run_tests"),
    "research": ("web_search", "memory_search"),
    "personal_productivity": ("memory_search", "calendar_create", "email_draft", "web_search"),
    "interview": ("memory_search", "web_search", "read_file"),
    "general": ("memory_search", "web_search"),
}


def list_tools(category: str | None = None, include_disabled: bool = False) -> list[dict[str, Any]]:
    tools = TOOLS
    if category:
        tools = tuple(tool for tool in tools if tool.category == category)
    if not include_disabled:
        tools = tuple(tool for tool in tools if tool.enabled)
    return [tool.public_dict() for tool in tools]


def detect_intents(prompt: str, selected_mode: str | None = None) -> list[str]:
    text = f"{selected_mode or ''} {prompt or ''}".lower()
    intents: list[str] = []
    if selected_mode in {"code", "design", "deploy"}:
        intents.append("software_implementation")
    if selected_mode == "research":
        intents.append("research")
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords) and intent not in intents:
            intents.append(intent)
    return intents or ["general"]


def select_tools(
    prompt: str,
    selected_mode: str | None = None,
    max_tools: int = 8,
    include_high_risk: bool = True,
) -> dict[str, Any]:
    intents = detect_intents(prompt, selected_mode)
    selected_names: list[str] = []
    reasons: dict[str, list[str]] = {}
    for intent in intents:
        for tool_name in INTENT_TOOLS.get(intent, ()):
            tool = TOOL_REGISTRY.get(tool_name)
            if not tool or not tool.enabled:
                continue
            if not include_high_risk and tool.risk_level in {"high", "critical"}:
                continue
            if tool_name not in selected_names:
                selected_names.append(tool_name)
            reasons.setdefault(tool_name, []).append(intent)

    selected_tools = [TOOL_REGISTRY[name] for name in selected_names[: max(1, min(max_tools, 20))]]
    return {
        "intents": intents,
        "tools": [tool.public_dict() for tool in selected_tools],
        "llm_tools": [tool.llm_tool_schema() for tool in selected_tools],
        "permission_summary": summarize_permissions(selected_tools),
        "selection_reasons": {tool.name: reasons.get(tool.name, []) for tool in selected_tools},
    }


def summarize_permissions(tools: list[AgentTool]) -> dict[str, Any]:
    buckets = {
        "automatic": [],
        "confirm_once": [],
        "always_confirm": [],
        "prohibited": [],
    }
    highest_risk = "low"
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for tool in tools:
        buckets[tool.permission].append(tool.name)
        if risk_order[tool.risk_level] > risk_order[highest_risk]:
            highest_risk = tool.risk_level
    return {
        "automatic": buckets["automatic"],
        "confirm_once": buckets["confirm_once"],
        "always_confirm": buckets["always_confirm"],
        "prohibited": buckets["prohibited"],
        "highest_risk": highest_risk,
        "requires_user_review": bool(buckets["confirm_once"] or buckets["always_confirm"]),
    }


def validate_tool_request(tool_name: str, approved: bool = False) -> dict[str, Any]:
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        return {"allowed": False, "requires_approval": False, "reason": "Unknown tool."}
    if tool.permission == "prohibited":
        return {"allowed": False, "requires_approval": False, "reason": "Tool is prohibited by default."}
    if tool.permission == "automatic":
        return {"allowed": True, "requires_approval": False, "reason": "Automatic low-risk tool."}
    if approved:
        return {"allowed": True, "requires_approval": False, "reason": "User approval supplied."}
    return {
        "allowed": False,
        "requires_approval": True,
        "reason": f"{tool.permission} tool requires explicit user approval.",
    }
