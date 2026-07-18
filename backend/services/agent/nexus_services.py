from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .intelligence_core import arceus_system_prompt
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
        f"{arceus_system_prompt('chat')}\n\n"
        "Answer with senior-level judgment, direct human language, and practical next steps. "
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
        "transparency_note": "These are editable memories Arceus can use for personalization. Archive or edit anything inaccurate.",
    }


def generate_code_task(kind: str, instruction: str, context: str, config: NexusLLMConfig) -> dict[str, Any]:
    system = (
        f"{arceus_system_prompt('code')}\n\n"
        "Return practical, production-ready engineering output. "
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
        f"{arceus_system_prompt('code')}\n\nExplain code in clear human language with key risks and next steps.",
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
        "You are Arceus UI/UX Studio. Generate professional, accessible UI guidance and React/Next.js-ready structure. Avoid decorative clutter.",
        f"Output type: {output_type}\nDesign request:\n{description}\nReturn sections: UX intent, layout, components, motion, accessibility, and starter code.",
        config,
    )
    return {"status": "draft", "output_type": output_type, "content": content}


def design_preview_html(description: str, style: str, content: str = "") -> str:
    style_key = style.lower()
    palettes = {
        "minimal": {
            "bg": "#f7f8fb",
            "surface": "#ffffff",
            "text": "#111827",
            "muted": "#64748b",
            "accent": "#2563eb",
            "border": "#e5e7eb",
        },
        "bold": {
            "bg": "#09090b",
            "surface": "#18181b",
            "text": "#fafafa",
            "muted": "#a1a1aa",
            "accent": "#f97316",
            "border": "#3f3f46",
        },
        "glass": {
            "bg": "linear-gradient(135deg,#07111f,#182445 46%,#0f172a)",
            "surface": "rgba(255,255,255,.12)",
            "text": "#f8fafc",
            "muted": "#cbd5e1",
            "accent": "#7dd3fc",
            "border": "rgba(255,255,255,.2)",
        },
    }
    colors = palettes.get(style_key, palettes["minimal"])
    clean_description = " ".join(description.split())[:180] or "Professional AI workspace interface"
    safe_title = f"{style.title()} Concept"
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
*{{box-sizing:border-box}} body{{margin:0;font-family:Inter,system-ui,sans-serif;background:{colors['bg']};color:{colors['text']};}}
.wrap{{min-height:100vh;padding:22px;display:grid;gap:16px;align-content:start}}
.nav,.card,.panel{{border:1px solid {colors['border']};background:{colors['surface']};border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.18)}}
.nav{{height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 16px;backdrop-filter:blur(16px)}}
.brand{{font-weight:800;letter-spacing:.02em}} .pill{{font-size:12px;color:{colors['accent']};border:1px solid {colors['border']};padding:6px 10px;border-radius:999px}}
.hero{{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;align-items:stretch}}
.card{{padding:20px;backdrop-filter:blur(18px)}} h1{{font-size:30px;line-height:1.05;margin:0 0 10px}} p{{color:{colors['muted']};line-height:1.5;margin:0}}
.actions{{display:flex;gap:8px;margin-top:18px}} button{{border:0;background:{colors['accent']};color:white;padding:10px 13px;border-radius:10px;font-weight:700}} button.secondary{{background:transparent;color:{colors['text']};border:1px solid {colors['border']}}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}} .metric{{padding:14px;border:1px solid {colors['border']};border-radius:12px;background:rgba(255,255,255,.05)}} .metric strong{{display:block;font-size:20px}}
.panel{{padding:16px;display:grid;gap:10px}} .row{{height:10px;border-radius:99px;background:{colors['border']}}} .row:nth-child(2){{width:84%}} .row:nth-child(3){{width:62%}} .row:nth-child(4){{width:74%}}
@media(max-width:720px){{.hero{{grid-template-columns:1fr}} h1{{font-size:24px}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="nav"><span class="brand">Arceus</span><span class="pill">{safe_title}</span></div>
  <section class="hero">
    <div class="card">
      <h1>{clean_description}</h1>
      <p>Clean hierarchy, focused actions, responsive layout, and polished interaction states prepared for implementation.</p>
      <div class="actions"><button>Primary Action</button><button class="secondary">Preview</button></div>
    </div>
    <div class="panel">
      <div class="metrics">
        <div class="metric"><strong>98%</strong><span>Health</span></div>
        <div class="metric"><strong>24</strong><span>Tasks</span></div>
        <div class="metric"><strong>7</strong><span>Signals</span></div>
      </div>
      <div class="row"></div><div class="row"></div><div class="row"></div><div class="row"></div>
    </div>
  </section>
</div>
</body>
</html>"""


def design_variants(description: str, output_type: str, config: NexusLLMConfig) -> dict[str, Any]:
    variants = []
    for style in ["minimal", "bold", "glass"]:
        prompt = f"{description}\n\nStyle direction: {style}. Return concise implementation notes and React/HTML/CSS starter code."
        response = design_response(prompt, output_type, config)
        content = response.get("content", "")
        variants.append({
            "style": style,
            "title": f"{style.title()} variant",
            "content": content,
            "preview_html": design_preview_html(description, style, content),
        })
    return {"variants": variants}


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
