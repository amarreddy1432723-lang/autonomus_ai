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
