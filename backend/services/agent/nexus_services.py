from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_router import get_chat_llm


FREE_TIER_CATALOG: list[dict[str, Any]] = [
    {
        "name": "Groq",
        "category": "LLM",
        "free_tier": "Free developer tier with rate limits",
        "best_for": "Fast interview, chat, and coding answers",
        "setup_notes": "Create an API key and configure GROQ_API_KEY.",
    },
    {
        "name": "Google Gemini",
        "category": "LLM / Multimodal",
        "free_tier": "Free API quota varies by model",
        "best_for": "Multimodal reasoning, fast chat, image understanding",
        "setup_notes": "Create a Google AI Studio key and configure GOOGLE_API_KEY.",
    },
    {
        "name": "Supabase",
        "category": "Database / Auth / Storage",
        "free_tier": "Free Postgres project with Auth and Storage limits",
        "best_for": "Prototype databases, auth, and file storage",
        "setup_notes": "Create a project, copy the URL and service role key into integrations.",
    },
    {
        "name": "Neon",
        "category": "Database",
        "free_tier": "Serverless Postgres free tier",
        "best_for": "Postgres apps with branching workflows",
        "setup_notes": "Create a database and configure DATABASE_URL.",
    },
    {
        "name": "Vercel",
        "category": "Hosting",
        "free_tier": "Hobby tier for frontend and serverless projects",
        "best_for": "Next.js frontend deployments",
        "setup_notes": "Connect GitHub repo and set frontend env vars.",
    },
    {
        "name": "Railway",
        "category": "Hosting",
        "free_tier": "Trial credits and usage-based hosting",
        "best_for": "FastAPI services, workers, Redis, databases",
        "setup_notes": "Connect GitHub repo, configure start command and env vars.",
    },
    {
        "name": "Render",
        "category": "Hosting",
        "free_tier": "Free web services with cold starts",
        "best_for": "Blueprint deployments and simple backend hosting",
        "setup_notes": "Use render.yaml and configure secrets in dashboard.",
    },
    {
        "name": "Resend",
        "category": "Email",
        "free_tier": "Developer email quota",
        "best_for": "Transactional emails and auth emails",
        "setup_notes": "Verify a domain or use test mode, then configure RESEND_API_KEY.",
    },
    {
        "name": "Cloudflare R2",
        "category": "Storage",
        "free_tier": "Generous object storage free tier",
        "best_for": "Private file uploads and generated assets",
        "setup_notes": "Create bucket and S3-compatible credentials.",
    },
    {
        "name": "E2B",
        "category": "Code Sandbox",
        "free_tier": "Free compute allocation for sandboxes",
        "best_for": "Safe code execution and agent workspaces",
        "setup_notes": "Create an API key and configure E2B_API_KEY before enabling execution.",
    },
]


@dataclass
class NexusLLMConfig:
    provider: str | None = None
    model: str | None = None


def _invoke_structured(system: str, prompt: str, config: NexusLLMConfig) -> str:
    llm = get_chat_llm(role="reasoning", provider=config.provider, model=config.model)
    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ])
    return str(response.content)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "nexus-task"


def classify_task_type(prompt: str) -> str:
    lowered = prompt.lower()
    if any(term in lowered for term in ["debug", "stack trace", "error", "exception", "failing test"]):
        return "debug"
    if any(term in lowered for term in ["code", "function", "api", "component", "typescript", "python", "sql", "bug"]):
        return "code"
    if any(term in lowered for term in ["design", "ui", "ux", "landing page", "animation", "layout"]):
        return "design"
    if any(term in lowered for term in ["research", "latest", "compare", "pricing", "news", "competitor"]):
        return "research"
    if any(term in lowered for term in ["interview", "resume", "tell me about yourself", "behavioral"]):
        return "interview"
    if any(term in lowered for term in ["deploy", "vercel", "railway", "render", "netlify"]):
        return "deploy"
    return "general"


def choose_model_for_task(task_type: str, speed_priority: bool = True) -> dict[str, str]:
    if speed_priority and task_type in {"interview", "general", "research"}:
        return {"provider": "groq", "model": "llama-3.3-70b-versatile", "reason": "Fast first-token response for live interaction."}
    if task_type in {"code", "debug"}:
        return {"provider": "openai", "model": "gpt-4o-mini", "reason": "Code and debugging benefit from stronger structured reasoning."}
    if task_type == "design":
        return {"provider": "anthropic", "model": "claude-3-5-haiku-20241022", "reason": "Design and writing benefit from critique-style language."}
    return {"provider": "autonomus", "model": "autonomus-ai-v1", "reason": "Default branded model with private fallback routing."}


def score_answer(prompt: str, answer: str) -> dict[str, Any]:
    score = 50
    lowered = answer.lower()
    if len(answer.strip()) > 120:
        score += 10
    if any(marker in lowered for marker in ["example", "for example", "because", "tradeoff", "edge case"]):
        score += 12
    if "as an ai" in lowered or "i cannot" in lowered:
        score -= 12
    if any(term in prompt.lower() for term in ["code", "debug", "api"]) and "```" in answer:
        score += 8
    if len(answer) > 3000:
        score -= 8
    score = max(0, min(100, score))
    return {
        "score": score,
        "passed": score >= 70,
        "checks": {
            "substantial": len(answer.strip()) > 120,
            "has_reasoning_or_example": any(marker in lowered for marker in ["example", "because", "tradeoff", "edge case"]),
            "avoids_ai_disclaimer": "as an ai" not in lowered,
            "not_overlong": len(answer) <= 3000,
        },
    }


def blended_answer(prompt: str, context: str, task_type: str, config: NexusLLMConfig | None = None) -> dict[str, Any]:
    selected = choose_model_for_task(task_type or classify_task_type(prompt))
    primary_config = config or NexusLLMConfig(selected["provider"], selected["model"])
    system = (
        "You are NEXUS AI. Answer with senior-level judgment, direct human language, and practical next steps. "
        "Use the provided context when relevant. Avoid hype, filler, and unsupported claims."
    )
    answer = _invoke_structured(system, f"Request:\n{prompt}\n\nContext:\n{context[:24000]}", primary_config)
    evaluation = score_answer(prompt, answer)
    improved = answer
    critique = ""

    if not evaluation["passed"]:
        critique_prompt = (
            "Improve this answer so it is more useful, direct, specific, and trustworthy. "
            "Preserve correct technical details and do not invent facts.\n\n"
            f"User request:\n{prompt}\n\nDraft answer:\n{answer}"
        )
        improved = _invoke_structured(system, critique_prompt, primary_config)
        critique = "Auto-improved because self-evaluation score was below threshold."
        evaluation = score_answer(prompt, improved)

    return {
        "task_type": task_type,
        "selected_model": selected,
        "answer": improved,
        "draft_answer": answer,
        "evaluation": evaluation,
        "critique": critique,
    }


def memory_transparency_summary(memories: list[Any]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    top_items = []
    for memory in memories:
        memory_type = getattr(memory, "memory_type", None) or getattr(memory, "type", "fact")
        by_type[memory_type] = by_type.get(memory_type, 0) + 1
        top_items.append({
            "id": str(memory.id),
            "type": memory_type,
            "content": memory.content,
            "confidence": float(memory.confidence or 0),
            "importance": int(memory.importance or 0),
            "tags": memory.tags or [],
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
        })
    top_items.sort(key=lambda item: (item["importance"], item["confidence"]), reverse=True)
    return {
        "total": len(memories),
        "by_type": by_type,
        "top_memories": top_items[:20],
        "transparency_note": "These are editable memories NEXUS can use for personalization. Archive or edit anything inaccurate.",
    }


def generate_code_task(kind: str, instruction: str, context: str, config: NexusLLMConfig) -> dict[str, Any]:
    system = (
        "You are NEXUS Code Engine. Return practical, production-ready engineering output. "
        "For generation and refactors, include a concise plan and unified diff-style patches. "
        "For debugging, identify root cause, fix, and tests. For code execution requests, do not claim execution unless logs are provided."
    )
    prompt = f"Task type: {kind}\nInstruction:\n{instruction}\n\nProject context:\n{context[:30000]}"
    content = _invoke_structured(system, prompt, config)
    return {
        "task_id": f"{_safe_slug(kind)}-{int(datetime.now(timezone.utc).timestamp())}",
        "kind": kind,
        "status": "draft",
        "requires_approval": kind in {"generate", "debug", "refactor", "test"},
        "content": content,
    }


def explain_code(instruction: str, context: str, config: NexusLLMConfig) -> dict[str, Any]:
    content = _invoke_structured(
        "You are NEXUS Code Explainer. Explain code in clear human language with key risks and next steps.",
        f"Explain request:\n{instruction}\n\nCode context:\n{context[:30000]}",
        config,
    )
    return {"status": "completed", "explanation": content}


def build_research_report(query: str, search_results: list[dict[str, Any]]) -> str:
    if not search_results:
        return f"# Research Report\n\nNo live results were available for **{query}**. Try adding a SERPER_API_KEY for richer research."
    lines = [f"# Research Report: {query}", "", "## Key Findings"]
    for index, item in enumerate(search_results[:8], start=1):
        title = item.get("title") or item.get("name") or "Untitled"
        snippet = item.get("snippet") or item.get("description") or ""
        link = item.get("link") or item.get("url") or ""
        lines.append(f"{index}. **{title}**")
        if snippet:
            lines.append(f"   {snippet}")
        if link:
            lines.append(f"   Source: {link}")
    lines.extend(["", "## Recommended Next Step", "Pick the most relevant source, verify it, then turn it into an action plan."])
    return "\n".join(lines)


def browse_summary(url: str, content: str) -> dict[str, Any]:
    return {
        "url": url,
        "status": "read_only_extract",
        "title": "",
        "summary": content[:5000],
        "requires_approval_for_actions": True,
    }


def recommend_free_tiers(project_type: str, needs: str = "") -> list[dict[str, Any]]:
    text = f"{project_type} {needs}".lower()
    ranked = []
    for item in FREE_TIER_CATALOG:
        score = 0
        haystack = json.dumps(item).lower()
        for token in re.findall(r"[a-z0-9]+", text):
            if len(token) > 2 and token in haystack:
                score += 1
        ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:6]]


def design_response(description: str, output_type: str, config: NexusLLMConfig) -> dict[str, Any]:
    content = _invoke_structured(
        "You are NEXUS UI/UX Studio. Generate professional, accessible UI guidance and React/Next.js-ready structure. Avoid decorative clutter.",
        f"Output type: {output_type}\nDesign request:\n{description}\nReturn sections: UX intent, layout, components, motion, accessibility, and starter code.",
        config,
    )
    return {"status": "draft", "output_type": output_type, "content": content}


def deployment_analysis(project_type: str, repo_context: str = "") -> dict[str, Any]:
    project = project_type.lower()
    if "next" in project or "react" in project:
        primary = "Vercel"
    elif "fastapi" in project or "python" in project:
        primary = "Railway"
    else:
        primary = "Render"
    return {
        "recommended_provider": primary,
        "alternatives": ["Railway", "Render", "Vercel", "Netlify"],
        "risk_level": "high_requires_approval",
        "steps": [
            "Verify build and start commands.",
            "Collect required environment variables.",
            "Create deployment project through provider API or dashboard.",
            "Deploy from GitHub and monitor logs.",
            "Rollback if health check fails.",
        ],
        "repo_context_preview": repo_context[:1200],
    }


def safety_check(content: str, action: str = "answer") -> dict[str, Any]:
    lowered = f"{action} {content}".lower()
    critical_terms = ["csam", "child sexual", "doxx", "steal password", "malware", "ransomware"]
    high_terms = ["delete database", "send email", "deploy production", "charge card", "financial transaction"]
    if any(term in lowered for term in critical_terms):
        return {"allowed": False, "risk": "critical", "reason": "Blocked unsafe content or action."}
    if any(term in lowered for term in high_terms):
        return {"allowed": True, "risk": "high", "requires_approval": True, "reason": "High-impact action requires approval."}
    return {"allowed": True, "risk": "low", "requires_approval": False, "reason": "No elevated risk detected."}


def proactive_suggestions(context: str = "") -> list[dict[str, Any]]:
    base = [
        ("Secure file uploads", "Add size, type, and antivirus checks before production-scale uploads.", "security"),
        ("Add usage budgets", "Set daily token and cost caps per user to avoid surprise spend.", "cost"),
        ("Improve deployment health", "Add post-deploy smoke checks for frontend, agent, auth, and goals services.", "deploy"),
        ("Add interview latency telemetry", "Track speech pause, first-token time, and full-answer time.", "interview"),
    ]
    if "code" in context.lower():
        base.insert(0, ("Generate tests", "Create focused tests for the code changes before applying patches.", "code"))
    return [
        {"id": _safe_slug(title), "title": title, "detail": detail, "category": category, "priority": index + 1}
        for index, (title, detail, category) in enumerate(base)
    ]
