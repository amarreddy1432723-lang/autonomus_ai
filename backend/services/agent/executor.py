import json
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from services.shared.models import Task, Approval, TaskExecution
from .approval import assess_task_risk
from .tools import web_search
from .reflection import run_aar_reflection

def run_task_execution(db: Session, task: Task) -> bool:
    """
    Simulates executing a task using the tool registry.
    Writes logs to the task_executions table.
    """
    try:
        agent_type = task.assigned_agent or "CodingAgent"
        tool_name = "web_search"
        tool_input = f"{task.title}: {task.description}"
        
        # If it is a research agent, call web search
        if agent_type == "ResearchAgent":
            tool_name = "web_search"
            # Call Serper tool
            try:
                tool_output = web_search.invoke({"query": task.title})
            except Exception as e:
                tool_output = f"Tool failure: {e}"
        else:
            # Emulate coding / configuration tool output
            tool_name = "write_file"
            tool_output = f"Success: Completed implementation of task '{task.title}'."
            
        # Record execution log
        execution = TaskExecution(
            task_id=task.id,
            user_id=task.user_id,
            agent_type=agent_type,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=str(tool_output),
            status="completed",
            success=True,
            completed_at=datetime.utcnow(),
        )
        db.add(execution)
        return True
    except Exception as e:
        # Record execution failure
        execution = TaskExecution(
            task_id=task.id,
            user_id=task.user_id,
            agent_type=task.assigned_agent or "CodingAgent",
            tool_name="unknown",
            tool_input=task.title,
            tool_output=f"Error executing: {e}",
            status="failed",
            success=False,
            completed_at=datetime.utcnow(),
        )
        db.add(execution)
        return False

def execute_pending_tasks(db: Session, user_id: UUID):
    """
    Picks up queued tasks for the user.
    If high risk and not yet approved, redirects to approvals gating.
    If low/medium or already approved, runs execution.
    """
    queued_tasks = db.query(Task).filter(
        Task.user_id == user_id,
        Task.status == "queued"
    ).order_by(Task.priority_score.desc()).all()
    
    # Sort queued_tasks topologically to execute dependencies first
    task_map = {t.id: t for t in queued_tasks}
    adj = {t.id: [] for t in queued_tasks}
    in_degree = {t.id: 0 for t in queued_tasks}
    
    for t in queued_tasks:
        for dep in t.dependencies:
            if dep.id in task_map:
                adj[dep.id].append(t.id)
                in_degree[t.id] += 1
                
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    queue.sort(key=lambda tid: task_map[tid].priority_score, reverse=True)
    
    topo_ordered = []
    while queue:
        curr_id = queue.pop(0)
        topo_ordered.append(task_map[curr_id])
        for neighbor in adj[curr_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                queue.sort(key=lambda tid: task_map[tid].priority_score, reverse=True)
                
    if len(topo_ordered) == len(queued_tasks):
        queued_tasks = topo_ordered

    # Fetch all approved records for this user
    approved_records = db.query(Approval).filter(
        Approval.user_id == user_id,
        Approval.status == "approved"
    ).all()
    approved_task_ids = {appr.payload.get("task_id") for appr in approved_records if appr.payload}
    
    results = []
    
    for task in queued_tasks:
        # Check predecessor dependencies
        is_blocked = False
        has_failed_dep = False
        failed_dep_title = ""
        
        for dep in task.dependencies:
            if dep.status == "failed":
                has_failed_dep = True
                failed_dep_title = dep.title
                break
            elif dep.status != "done":
                is_blocked = True
                
        if has_failed_dep:
            task.status = "failed"
            execution = TaskExecution(
                task_id=task.id,
                user_id=user_id,
                agent_type=task.assigned_agent or "CodingAgent",
                tool_name="dependency_check",
                tool_input=task.title,
                tool_output=f"Task failed automatically because its predecessor dependency '{failed_dep_title}' failed.",
                status="failed",
                success=False
            )
            db.add(execution)
            db.commit()
            results.append({
                "task_id": str(task.id),
                "status": "failed",
                "action": "failed_due_to_dependency"
            })
            continue
            
        if is_blocked:
            results.append({
                "task_id": str(task.id),
                "status": "queued",
                "action": "skipped_blocked_by_dependency"
            })
            continue

        # Check if task was already approved
        has_approval = str(task.id) in approved_task_ids
        
        risk = "LOW"
        if not has_approval:
            risk = assess_task_risk(task.title, task.description, db=db, user_id=user_id)
        
        if risk == "HIGH":
            # Gated behind Approval System
            task.status = "waiting_approval"
            
            # Create Approval record
            approval = Approval(
                user_id=user_id,
                task_id=task.id,
                requested_by_agent="execution",
                action_type="task_execution",
                payload={
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "task_description": task.description
                },
                action_description=f"Execute task: {task.title}",
                action_payload={
                    "task_id": str(task.id),
                    "task_title": task.title,
                    "task_description": task.description
                },
                risk_level="high",
                risk_reasoning="Executor risk assessment classified this task as HIGH.",
                status="pending"
            )
            db.add(approval)
            db.commit()
            
            results.append({
                "task_id": str(task.id),
                "status": "waiting_approval",
                "action": "approval_required"
            })
        else:
            # Low/Med risk or already approved: run task execution immediately
            task.status = "in_progress"
            db.commit()
            
            success = run_task_execution(db, task)
            
            if success:
                task.status = "done"
            else:
                task.status = "failed"
                
            db.commit()
            
            # Trigger After Action Review (AAR) reflection
            try:
                run_aar_reflection(db, task, success)
            except Exception as aar_err:
                print(f"[Reflection Error] Failed to run AAR reflection: {aar_err}")
                
            results.append({
                "task_id": str(task.id),
                "status": task.status,
                "action": "executed"
            })
            
    return results
