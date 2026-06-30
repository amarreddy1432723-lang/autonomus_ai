import json
from uuid import UUID
from typing import List, Dict, Any
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from .llm_router import get_chat_llm
from .config import settings

def decompose_goal(user_id: UUID, goal_title: str, goal_desc: str, goal_deadline: datetime = None) -> List[Dict[str, Any]]:
    """
    Decomposes a user goal into a list of structured, executable tasks.
    Calculates PERT estimates, runs CPM, and computes priority scores.
    """
    llm = get_chat_llm(role="planning")
    is_mock = settings.LLM_PROVIDER.lower() in ("", "mock")
    
    if is_mock:
        # Standard mock decomposition based on keywords
        tasks = []
        desc_lower = goal_desc.lower() if goal_desc else ""
        title_lower = goal_title.lower()
        
        if "saas" in title_lower or "landing" in title_lower or "web" in title_lower:
            tasks = [
                {
                    "title": "Research landing page layouts and pricing sections",
                    "description": "Search competitor pricing sections to compile average SaaS subscription price ranges.",
                    "assigned_agent": "ResearchAgent",
                    "optimistic_estimate": 1.0,
                    "most_likely_estimate": 2.0,
                    "pessimistic_estimate": 4.0,
                    "priority_score": 0.9,
                    "dependencies": []
                },
                {
                    "title": "Set up auth provider credentials",
                    "description": "Create credentials and API keys for auth provider (e.g. Clerk). HIGH risk action, requires secrets handling.",
                    "assigned_agent": "CodingAgent",
                    "optimistic_estimate": 1.0,
                    "most_likely_estimate": 1.5,
                    "pessimistic_estimate": 3.0,
                    "priority_score": 0.8,
                    "dependencies": []
                },
                {
                    "title": "Build frontend login button",
                    "description": "Construct the JSX components mapping the login routing button layout.",
                    "assigned_agent": "CodingAgent",
                    "optimistic_estimate": 0.5,
                    "most_likely_estimate": 1.0,
                    "pessimistic_estimate": 2.0,
                    "priority_score": 0.7,
                    "dependencies": [
                        "Research landing page layouts and pricing sections",
                        "Set up auth provider credentials"
                    ]
                }
            ]
        else:
            tasks = [
                {
                    "title": f"Analyze goal: {goal_title}",
                    "description": f"Gather requirements and outline dependencies for: {goal_desc}",
                    "assigned_agent": "ResearchAgent",
                    "optimistic_estimate": 1.0,
                    "most_likely_estimate": 2.0,
                    "pessimistic_estimate": 3.0,
                    "priority_score": 0.9,
                    "dependencies": []
                },
                {
                    "title": f"Execute core project details",
                    "description": f"Implement the baseline tasks necessary for: {goal_title}",
                    "assigned_agent": "CodingAgent",
                    "optimistic_estimate": 2.0,
                    "most_likely_estimate": 4.0,
                    "pessimistic_estimate": 8.0,
                    "priority_score": 0.8,
                    "dependencies": [f"Analyze goal: {goal_title}"]
                }
            ]
    else:
        system_prompt = (
            "You are a master project planning agent. Your task is to decompose a goal into a flat list of individual tasks.\n"
            "Respond strictly in JSON format representing a list of tasks. Each task must have the following schema:\n"
            "{\n"
            "  \"title\": \"string\",\n"
            "  \"description\": \"string\",\n"
            "  \"assigned_agent\": \"ResearchAgent\" | \"CodingAgent\" | \"SchedulerAgent\",\n"
            "  \"optimistic_estimate\": float (hours),\n"
            "  \"most_likely_estimate\": float (hours),\n"
            "  \"pessimistic_estimate\": float (hours),\n"
            "  \"priority_score\": float (0.0 to 1.0),\n"
            "  \"dependencies\": [\"string\"] (list of predecessor task titles that this task depends on)\n"
            "}\n"
            "Limit the output to 3-6 logical tasks."
        )
        
        goal_prompt = f"Goal Title: {goal_title}\nGoal Description: {goal_desc}"
        
        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=goal_prompt)
            ], response_format={"type": "json_object"})
            
            tasks = json.loads(response.content)
            if isinstance(tasks, dict) and "tasks" in tasks:
                tasks = tasks["tasks"]
            elif not isinstance(tasks, list):
                tasks = []
        except Exception as e:
            print(f"Error invoking Planner LLM: {e}")
            tasks = []

    if not tasks:
        tasks = [
            {
                "title": f"Clarify success criteria for {goal_title}",
                "description": f"Turn the goal into measurable outcomes, constraints, and review checkpoints: {goal_desc}",
                "assigned_agent": "ResearchAgent",
                "optimistic_estimate": 1.0,
                "most_likely_estimate": 2.0,
                "pessimistic_estimate": 3.0,
                "priority_score": 0.9,
                "dependencies": []
            },
            {
                "title": f"Build the core plan for {goal_title}",
                "description": "Create the main project structure, task sequence, and execution path.",
                "assigned_agent": "PlanningAgent",
                "optimistic_estimate": 2.0,
                "most_likely_estimate": 4.0,
                "pessimistic_estimate": 7.0,
                "priority_score": 0.85,
                "dependencies": [f"Clarify success criteria for {goal_title}"]
            },
            {
                "title": f"Review and improve {goal_title}",
                "description": "Check quality, resolve gaps, and prepare the next execution checkpoint.",
                "assigned_agent": "ResearchAgent",
                "optimistic_estimate": 1.0,
                "most_likely_estimate": 2.0,
                "pessimistic_estimate": 4.0,
                "priority_score": 0.7,
                "dependencies": [f"Build the core plan for {goal_title}"]
            }
        ]
            
    # Calculate PERT estimates for all tasks
    for task in tasks:
        opt = float(task.get("optimistic_estimate", 1.0))
        likely = float(task.get("most_likely_estimate", 2.0))
        pess = float(task.get("pessimistic_estimate", 3.0))
        
        pert = (opt + 4.0 * likely + pess) / 6.0
        task["pert_estimate"] = round(pert, 2)
        
    # Calculate CPM (Critical Path Method)
    calculate_cpm(tasks)
    
    # Calculate Composite Priority Score
    calculate_priority_scores(tasks, goal_deadline)
        
    return tasks

def validate_no_cycles(tasks: List[Dict[str, Any]]) -> bool:
    """
    Kahn's algorithm for topological sorting to validate a DAG has no cycles.
    """
    adj = {}
    in_degree = {}
    
    for t in tasks:
        title = t["title"]
        adj[title] = []
        in_degree[title] = 0
        
    for t in tasks:
        title = t["title"]
        deps = t.get("dependencies", [])
        for dep in deps:
            if dep in adj:
                adj[dep].append(title)
                in_degree[title] += 1
                
    queue = [node for node, deg in in_degree.items() if deg == 0]
    visited_count = 0
    
    while queue:
        curr = queue.pop(0)
        visited_count += 1
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                
    return visited_count == len(tasks)

def calculate_cpm(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes Critical Path Method values (ES, EF, LS, LF, float) and identifies critical path.
    Assumes tasks form a DAG.
    """
    adj = {}
    predecessors = {}
    in_degree = {}
    task_map = {}
    
    for t in tasks:
        title = t["title"]
        task_map[title] = t
        adj[title] = []
        predecessors[title] = []
        in_degree[title] = 0
        
    for t in tasks:
        title = t["title"]
        deps = t.get("dependencies", [])
        for dep in deps:
            if dep in task_map:
                adj[dep].append(title)
                predecessors[title].append(dep)
                in_degree[title] += 1
                
    queue = [node for node, deg in in_degree.items() if deg == 0]
    topo_order = []
    
    while queue:
        curr = queue.pop(0)
        topo_order.append(curr)
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                
    if len(topo_order) != len(tasks):
        return {}
        
    es = {}
    ef = {}
    for node in topo_order:
        t = task_map[node]
        dur = float(t.get("pert_estimate", t.get("most_likely_estimate", 1.0)))
        
        preds = predecessors[node]
        if not preds:
            es[node] = 0.0
        else:
            es[node] = max(ef[p] for p in preds)
        ef[node] = es[node] + dur
        
    project_duration = max(ef.values()) if ef else 0.0
    
    ls = {}
    lf = {}
    for node in reversed(topo_order):
        t = task_map[node]
        dur = float(t.get("pert_estimate", t.get("most_likely_estimate", 1.0)))
        
        succs = adj[node]
        if not succs:
            lf[node] = project_duration
        else:
            lf[node] = min(ls[s] for s in succs)
        ls[node] = lf[node] - dur
        
    for t in tasks:
        title = t["title"]
        t_es = es[title]
        t_ef = ef[title]
        t_ls = ls[title]
        t_lf = lf[title]
        t_float = round(t_ls - t_es, 2)
        
        if t_float < 0.01:
            t_float = 0.0
            
        t["es"] = round(t_es, 2)
        t["ef"] = round(t_ef, 2)
        t["ls"] = round(t_ls, 2)
        t["lf"] = round(t_lf, 2)
        t["float"] = t_float
        t["is_critical"] = (t_float == 0.0)
        
    return {
        "project_duration": round(project_duration, 2),
        "critical_path": [node for node in topo_order if ls[node] - es[node] < 0.01]
    }

def calculate_priority_scores(tasks: List[Dict[str, Any]], goal_deadline: datetime = None) -> None:
    """
    Computes a composite priority score (0.0 to 1.0) for each task based on:
    - Urgency (weight 0.35)
    - Importance (weight 0.30)
    - Dependency unblocking (weight 0.20)
    - Effort inverse (weight 0.10)
    - Momentum/Same domain (weight 0.05)
    """
    dependent_counts = {t["title"]: 0 for t in tasks}
    for t in tasks:
        for dep in t.get("dependencies", []):
            if dep in dependent_counts:
                dependent_counts[dep] += 1
                
    cpm_res = calculate_cpm(tasks)
    critical_tasks = cpm_res.get("critical_path", [])
    
    now = datetime.utcnow()
    
    for t in tasks:
        title = t["title"]
        dur = float(t.get("pert_estimate", 1.0))
        
        # Urgency
        urgency = 0.0
        if goal_deadline:
            # Strip timezone if present to compare offset-naive datetimes
            target_deadline = goal_deadline.replace(tzinfo=None)
            days_total = (target_deadline - now).days
            if days_total > 0:
                due = t.get("due_date") or target_deadline
                if isinstance(due, str):
                    try:
                        due = datetime.fromisoformat(due)
                    except ValueError:
                        due = target_deadline
                due = due.replace(tzinfo=None)
                days_left = (due - now).days
                urgency = max(0.0, 1.0 - (days_left / days_total))
            else:
                urgency = 1.0
        
        # Critical path bonus
        if title in critical_tasks:
            urgency += 0.2
        urgency = min(1.0, urgency)
        
        # Importance (from LLM or existing priority_score)
        importance = float(t.get("priority_score", 0.5))
        
        # Dependency score
        dep_count = dependent_counts[title]
        dependency_score = min(1.0, dep_count / 5.0)
        
        # Effort score (easy wins first)
        effort_score = max(0.0, 1.0 - (dur / 16.0))
        
        # Momentum score (baseline same domain)
        momentum_score = 0.5
        
        # Calculate composite score
        composite = (
            0.35 * urgency +
            0.30 * importance +
            0.20 * dependency_score +
            0.10 * effort_score +
            0.05 * momentum_score
        )
        
        t["priority_score"] = round(min(1.0, max(0.0, composite)), 2)


def infer_goal_category(goal_title: str, goal_desc: str | None = None) -> str:
    text = f"{goal_title} {goal_desc or ''}".lower()
    categories = {
        "software": ["app", "api", "code", "deploy", "backend", "frontend", "saas", "website", "mobile"],
        "learning": ["learn", "study", "course", "book", "roadmap", "practice", "interview"],
        "career": ["job", "career", "resume", "portfolio", "promotion", "engineer"],
        "business": ["startup", "customer", "revenue", "marketing", "sales", "launch"],
        "finance": ["money", "budget", "invest", "saving", "income"],
        "health": ["fitness", "health", "diet", "workout", "sleep"],
    }
    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "general"


def formalize_goal(
    user_id: UUID,
    goal_title: str,
    goal_desc: str | None = None,
    goal_deadline: datetime | None = None,
) -> Dict[str, Any]:
    category = infer_goal_category(goal_title, goal_desc)
    description = goal_desc or f"Complete the goal: {goal_title}"
    words = [word.strip(".,;:!?") for word in description.split() if len(word.strip(".,;:!?")) > 3]
    success_criteria = [
        f"Define measurable outcome for {goal_title}",
        "Complete all critical path tasks",
        "Review final result against the original goal",
    ]
    if goal_deadline:
        success_criteria.append(f"Finish before {goal_deadline.date().isoformat()}")

    constraints = []
    if "budget" in description.lower():
        constraints.append("Respect stated budget constraints")
    if "deadline" in description.lower() or goal_deadline:
        constraints.append("Protect deadline-sensitive tasks")

    ambiguity_score = 0.35 if len(words) >= 10 else 0.65
    priority = 4 if goal_deadline else 3
    return {
        "title": goal_title.strip(),
        "description": description.strip(),
        "category": category,
        "priority": priority,
        "success_criteria": success_criteria,
        "constraints": constraints,
        "assumptions": [
            "The plan can be refined as task execution results arrive",
            "External credentials or paid services require manual user approval",
        ],
        "ambiguity_score": ambiguity_score,
        "user_id": str(user_id),
    }


def generate_roadmap(
    goal_title: str,
    goal_desc: str | None = None,
    goal_deadline: datetime | None = None,
) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    if goal_deadline:
        total_days = max(7, (goal_deadline.replace(tzinfo=None) - now).days)
    else:
        total_days = 30
    phase_count = 4 if total_days >= 45 else 3
    phase_span = max(2, total_days // phase_count)

    labels = [
        ("Discovery", "Requirements and success criteria are clear"),
        ("Foundation", "Core structure and dependencies are ready"),
        ("Execution", "Main deliverables are implemented"),
        ("Review", "Quality checks and final improvements are complete"),
    ][:phase_count]

    roadmap = []
    for index, (title, milestone) in enumerate(labels, start=1):
        start_day = (index - 1) * phase_span
        end_day = total_days if index == phase_count else index * phase_span
        roadmap.append({
            "phase_number": index,
            "title": title,
            "milestone": milestone,
            "start_day": start_day,
            "end_day": end_day,
            "projects": [f"{title}: {goal_title}"],
        })
    return roadmap


def build_structured_plan(
    user_id: UUID,
    goal_title: str,
    goal_desc: str | None = None,
    goal_deadline: datetime | None = None,
) -> Dict[str, Any]:
    formal_goal = formalize_goal(user_id, goal_title, goal_desc, goal_deadline)
    roadmap = generate_roadmap(goal_title, goal_desc, goal_deadline)
    tasks = decompose_goal(user_id, goal_title, goal_desc or "", goal_deadline)
    cpm = calculate_cpm(tasks)

    projects = []
    phase_lookup = {}
    for phase in roadmap:
        project_title = phase["projects"][0]
        phase_lookup[phase["phase_number"]] = project_title
        projects.append({
            "title": project_title,
            "description": f"{phase['title']} work for {goal_title}",
            "phase_number": phase["phase_number"],
            "milestone": phase["milestone"],
            "lead_agent": "PlanningAgent",
            "dependencies": [],
        })

    for index, task in enumerate(tasks):
        phase_number = min(len(projects), index + 1)
        task["phase_number"] = phase_number
        task["project_title"] = phase_lookup[phase_number]
        task["success_criteria"] = [
            "Output is saved or reflected in the project state",
            "Result can be reviewed by the user",
        ]

    estimated_hours_total = round(sum(float(t.get("pert_estimate", 0.0)) for t in tasks), 2)
    health = calculate_plan_health(tasks)
    risk_flags = []
    if formal_goal["ambiguity_score"] > 0.6:
        risk_flags.append("Goal description is broad; early clarification task is important")
    if goal_deadline and estimated_hours_total / 4.0 > max(1, (goal_deadline.replace(tzinfo=None) - datetime.utcnow()).days):
        risk_flags.append("Estimated effort may be tight for the deadline")

    return {
        "formal_goal": formal_goal,
        "roadmap": roadmap,
        "projects": projects,
        "tasks": tasks,
        "critical_path": cpm.get("critical_path", []),
        "estimated_hours_total": estimated_hours_total,
        "plan_health_score": health["score"],
        "risk_flags": risk_flags,
        "assumptions": formal_goal["assumptions"],
        "created_at": datetime.utcnow().isoformat(),
    }


def calculate_plan_health(tasks: List[Any]) -> Dict[str, Any]:
    normalized = []
    for task in tasks:
        if isinstance(task, dict):
            normalized.append(task)
        else:
            normalized.append({
                "status": getattr(task, "status", "queued"),
                "priority_score": getattr(task, "priority_score", 0.0),
                "is_critical": getattr(task, "is_critical_path", False),
                "title": getattr(task, "title", ""),
            })

    total = len(normalized)
    if total == 0:
        return {"score": 0.0, "total_tasks": 0, "completed_tasks": 0, "blocked_tasks": 0, "risk_flags": []}

    completed = sum(1 for t in normalized if t.get("status") in ("done", "completed"))
    blocked = sum(1 for t in normalized if t.get("status") in ("blocked", "failed", "waiting_approval"))
    critical_open = sum(
        1 for t in normalized
        if (t.get("is_critical") or t.get("is_critical_path")) and t.get("status", "queued") not in ("done", "completed")
    )
    completion_score = completed / total
    blockage_penalty = min(0.4, blocked * 0.12)
    critical_penalty = min(0.25, critical_open * 0.05)
    score = round(max(0.0, min(1.0, 0.75 + completion_score * 0.25 - blockage_penalty - critical_penalty)), 2)
    risk_flags = []
    if blocked:
        risk_flags.append(f"{blocked} task(s) blocked or waiting")
    if critical_open:
        risk_flags.append(f"{critical_open} critical-path task(s) still open")
    return {
        "score": score,
        "total_tasks": total,
        "completed_tasks": completed,
        "blocked_tasks": blocked,
        "critical_open_tasks": critical_open,
        "risk_flags": risk_flags,
    }


def propose_replan(goal: Any, tasks: List[Any], trigger: str, strategy: str = "hybrid") -> Dict[str, Any]:
    health = calculate_plan_health(tasks)
    base_options = [
        {
            "strategy": "extend",
            "summary": "Protect scope and move the deadline or schedule more time.",
            "impact": "Lowest quality risk, higher calendar cost.",
        },
        {
            "strategy": "descope",
            "summary": "Keep the deadline and reduce non-critical deliverables.",
            "impact": "Fastest recovery, lower feature completeness.",
        },
        {
            "strategy": "crunch",
            "summary": "Keep scope and deadline by increasing daily effort.",
            "impact": "Useful briefly, high burnout risk.",
        },
        {
            "strategy": "hybrid",
            "summary": "Prioritize critical path, descope optional work, and add a review checkpoint.",
            "impact": "Balanced recovery path for most goals.",
        },
    ]
    recommended = strategy if strategy in {o["strategy"] for o in base_options} else "hybrid"
    if health["score"] < 0.55 and recommended == "crunch":
        recommended = "hybrid"
    return {
        "trigger": trigger,
        "health": health,
        "recommended_strategy": recommended,
        "options": base_options,
        "changes": [
            "Review blocked or failed tasks first",
            "Move highest priority critical-path tasks to the next execution batch",
            "Schedule a checkpoint after the next completed task",
        ],
        "generated_at": datetime.utcnow().isoformat(),
        "goal_id": str(getattr(goal, "id", "")),
    }
