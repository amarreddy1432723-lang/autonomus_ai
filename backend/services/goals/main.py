import jwt
import os
from typing import List
from uuid import UUID
from datetime import datetime
from fastapi import FastAPI, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.models import Goal, Task, Approval, Schedule, Project, Memory
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware
from services.shared.api import clamp_pagination, install_api_foundation
from services.shared.security import resolve_user_id_from_auth_or_clerk
from services.agent.planner import (
    build_structured_plan,
    calculate_plan_health,
    propose_replan,
    validate_no_cycles,
)
from services.agent.executor import execute_pending_tasks
from services.goals.config import settings
from services.goals.schemas import (
    GoalCreate, GoalResponse, TaskResponse, TaskUpdate, 
    ApprovalResponse, ApprovalResolve, ScheduleCreate, ScheduleResponse, GraphQLQuery,
    ReplanRequest,
)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.shared.database import SessionLocal, verify_default_user
    db = SessionLocal()
    try:
        verify_default_user(db)
    finally:
        db.close()
    yield

app = FastAPI(title="my-ai Goals Service", version="1.0.0", lifespan=lifespan)
install_api_foundation(app, "goals-service")
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

@app.get("/")
def service_root():
    return {
        "service": "goals-service",
        "status": "running",
        "message": "This is a NEXUS API service. Open the frontend UI instead.",
        "frontend": os.getenv("NEXUS_FRONTEND_URL", "http://localhost:3000/workspace"),
        "docs": "/docs",
    }

def get_current_user_id(
    authorization: str | None = Header(None), 
    x_user_id: str | None = Header(None, alias="x-user-id"),
    db: Session = Depends(get_db),
) -> UUID:
    return resolve_user_id_from_auth_or_clerk(db, authorization, x_user_id, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)

@app.post("/api/v1/goals", response_model=GoalResponse, status_code=201)
def create_goal(goal_in: GoalCreate, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    structured_plan = build_structured_plan(user_id, goal_in.title, goal_in.description, goal_in.deadline)
    formal_goal = structured_plan["formal_goal"]
    decomposed_tasks = structured_plan["tasks"]
    
    if not validate_no_cycles(decomposed_tasks):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decomposed plan contains circular dependencies."
        )

    success_criteria = goal_in.success_criteria or formal_goal["success_criteria"]
    constraints = goal_in.constraints or formal_goal["constraints"]
    assumptions = goal_in.assumptions or formal_goal["assumptions"]
    priority = goal_in.priority if goal_in.priority is not None else formal_goal["priority"]
    category = goal_in.category or formal_goal["category"]

    goal = Goal(
        user_id=user_id,
        title=goal_in.title,
        description=goal_in.description,
        category=category,
        priority=priority,
        deadline=goal_in.deadline,
        success_criteria=success_criteria,
        constraints=constraints,
        assumptions=assumptions,
        status="active",
        priority_score=max((float(t.get("priority_score", 0.0)) for t in decomposed_tasks), default=0.0),
        progress=0.0,
        progress_pct=0.0,
        plan_version=1,
        original_plan=structured_plan,
        current_plan=structured_plan,
        plan_change_log=[],
        estimated_hours_total=structured_plan["estimated_hours_total"],
    )
    db.add(goal)
    db.flush()

    saved_projects = {}
    for project_data in structured_plan["projects"]:
        project = Project(
            goal_id=goal.id,
            user_id=user_id,
            title=project_data["title"],
            description=project_data.get("description"),
            status="active" if project_data.get("phase_number") == 1 else "pending",
            phase_number=project_data.get("phase_number", 1),
            milestone=project_data.get("milestone"),
            lead_agent=project_data.get("lead_agent"),
            dependencies=project_data.get("dependencies", []),
        )
        db.add(project)
        saved_projects[project.title] = project
    
    db.flush()

    saved_tasks = {}
    for task_data in decomposed_tasks:
        opt = float(task_data.get("optimistic_estimate", 1.0))
        likely = float(task_data.get("most_likely_estimate", 2.0))
        pess = float(task_data.get("pessimistic_estimate", 3.0))
        pert = float(task_data.get("pert_estimate", (opt + 4.0 * likely + pess) / 6.0))
        std_dev = max(0.0, (pess - opt) / 6.0)
        project = saved_projects.get(task_data.get("project_title"))
        task = Task(
            project_id=project.id if project else None,
            goal_id=goal.id,
            user_id=user_id,
            title=task_data["title"],
            description=task_data["description"],
            assigned_agent=task_data["assigned_agent"],
            status="queued",
            priority_score=float(task_data.get("priority_score", 0.0)),
            pert_estimate=pert,
            optimistic_estimate=opt,
            most_likely_estimate=likely,
            pessimistic_estimate=pess,
            est_hours_optimistic=opt,
            est_hours_likely=likely,
            est_hours_pessimistic=pess,
            est_hours_pert=pert,
            est_hours_std_dev=round(std_dev, 2),
            is_critical_path=bool(task_data.get("is_critical", False)),
            float_hours=float(task_data.get("float", 0.0)),
            earliest_start_day=int(task_data.get("es", 0)),
            earliest_finish_day=int(task_data.get("ef", 0)),
            latest_start_day=int(task_data.get("ls", 0)),
            latest_finish_day=int(task_data.get("lf", 0)),
            success_criteria=task_data.get("success_criteria", []),
        )
        db.add(task)
        saved_tasks[task_data["title"]] = (task, task_data)
        
    db.flush()
    
    for title, (task, task_data) in saved_tasks.items():
        deps = task_data.get("dependencies", [])
        for dep_title in deps:
            if dep_title in saved_tasks:
                parent_task = saved_tasks[dep_title][0]
                task.dependencies.append(parent_task)
        
    db.commit()
    db.refresh(goal)
    return goal

@app.get("/api/v1/goals", response_model=List[GoalResponse])
def list_goals(
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    page, page_size, offset = clamp_pagination(page, page_size)
    query = db.query(Goal).filter(Goal.user_id == user_id)
    if status_filter:
        query = query.filter(Goal.status == status_filter)
    if category:
        query = query.filter(Goal.category == category)
    return query.order_by(Goal.created_at.desc()).offset(offset).limit(page_size).all()

@app.get("/api/v1/goals/{id}", response_model=GoalResponse)
def get_goal(id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal

@app.get("/api/v1/goals/{id}/plan")
def get_goal_plan(id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    projects = db.query(Project).filter(Project.goal_id == id, Project.user_id == user_id).order_by(Project.phase_number).all()
    tasks = db.query(Task).filter(Task.goal_id == id, Task.user_id == user_id).order_by(Task.earliest_start_day, Task.created_at).all()
    return {
        "goal_id": str(goal.id),
        "plan_version": goal.plan_version,
        "current_plan": goal.current_plan,
        "projects": projects,
        "tasks": tasks,
        "critical_path": [task.title for task in tasks if task.is_critical_path],
    }

@app.get("/api/v1/goals/{id}/health")
def get_goal_health(id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    tasks = db.query(Task).filter(Task.goal_id == id, Task.user_id == user_id).all()
    health = calculate_plan_health(tasks)
    return {
        "goal_id": str(goal.id),
        "title": goal.title,
        "status": goal.status,
        "plan_version": goal.plan_version,
        **health,
    }

@app.post("/api/v1/goals/{id}/replan")
def replan_goal(
    id: UUID,
    replan_in: ReplanRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    goal = db.query(Goal).filter(Goal.id == id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    tasks = db.query(Task).filter(Task.goal_id == id, Task.user_id == user_id).all()
    proposal = propose_replan(goal, tasks, replan_in.trigger, replan_in.strategy)
    change_log = list(goal.plan_change_log or [])
    change_log.append({
        "version": (goal.plan_version or 1) + 1,
        "trigger": replan_in.trigger,
        "strategy": proposal["recommended_strategy"],
        "created_at": proposal["generated_at"],
    })
    current_plan = dict(goal.current_plan or {})
    current_plan["last_replan"] = proposal
    goal.plan_version = (goal.plan_version or 1) + 1
    goal.plan_change_log = change_log
    goal.current_plan = current_plan
    db.commit()
    db.refresh(goal)
    return {
        "goal_id": str(goal.id),
        "plan_version": goal.plan_version,
        "proposal": proposal,
        "current_plan": goal.current_plan,
        "plan_change_log": goal.plan_change_log,
    }

@app.get("/api/v1/tasks", response_model=List[TaskResponse])
def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    assigned_agent: str | None = None,
    is_critical_path: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    page, page_size, offset = clamp_pagination(page, page_size)
    query = db.query(Task).filter(Task.user_id == user_id)
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if assigned_agent:
        query = query.filter(Task.assigned_agent == assigned_agent)
    if is_critical_path is not None:
        query = query.filter(Task.is_critical_path == is_critical_path)
    return query.order_by(Task.priority_score.desc(), Task.created_at.desc()).offset(offset).limit(page_size).all()

@app.patch("/api/v1/tasks/{id}", response_model=TaskResponse)
def update_task(id: UUID, task_in: TaskUpdate, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task_in.status is not None:
        task.status = task_in.status
    if task_in.priority_score is not None:
        task.priority_score = task_in.priority_score
        
    db.commit()
    db.refresh(task)
    return task

@app.post("/api/v1/tasks/run")
def trigger_task_runner(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    Triggers execution of queued tasks for the user.
    """
    results = execute_pending_tasks(db, user_id)
    return {"results": results}

@app.get("/api/v1/approvals", response_model=List[ApprovalResponse])
def list_approvals(
    status_filter: str | None = Query(None, alias="status"),
    page: int = 1,
    page_size: int = 20,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    page, page_size, offset = clamp_pagination(page, page_size)
    query = db.query(Approval).filter(Approval.user_id == user_id)
    if status_filter:
        query = query.filter(Approval.status == status_filter)
    return query.order_by(Approval.requested_at.desc()).offset(offset).limit(page_size).all()

@app.post("/api/v1/approvals/{id}/resolve", response_model=ApprovalResponse)
def resolve_approval(id: UUID, resolve_in: ApprovalResolve, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    approval = db.query(Approval).filter(Approval.id == id, Approval.user_id == user_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
        
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Approval request has already been resolved: {approval.status}")
        
    status_choice = resolve_in.status.lower()
    if status_choice not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be either 'approved' or 'rejected'")
        
    approval.status = status_choice
    approval.resolved_at = datetime.utcnow()
    
    # Update target task status
    task_id_str = approval.payload.get("task_id")
    if task_id_str:
        task = db.query(Task).filter(Task.id == UUID(task_id_str), Task.user_id == user_id).first()
        if task:
            if status_choice == "approved":
                # Queue it back for execution
                task.status = "queued"
            else:
                task.status = "failed"
                
    db.commit()
    db.refresh(approval)
    return approval

@app.get("/api/v1/schedules", response_model=List[ScheduleResponse])
def get_schedules(
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    page, page_size, offset = clamp_pagination(page, page_size)
    query = db.query(Schedule).filter(Schedule.user_id == user_id)
    if is_active is not None:
        query = query.filter(Schedule.is_active == is_active)
    return query.order_by(Schedule.next_run_at.asc()).offset(offset).limit(page_size).all()

@app.post("/api/v1/schedules", response_model=ScheduleResponse, status_code=201)
def create_schedule(schedule_in: ScheduleCreate, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    new_sched = Schedule(
        user_id=user_id,
        task_id=schedule_in.task_id,
        goal_id=schedule_in.goal_id,
        title=schedule_in.title,
        schedule_type=schedule_in.schedule_type,
        cron_expression=schedule_in.cron_expression,
        next_run_at=schedule_in.next_run_at,
        trigger_type=schedule_in.trigger_type,
        trigger_payload=schedule_in.trigger_payload,
        is_active=True
    )
    db.add(new_sched)
    db.commit()
    db.refresh(new_sched)
    return new_sched

@app.delete("/api/v1/schedules/{id}")
def delete_schedule(id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    sched = db.query(Schedule).filter(Schedule.id == id, Schedule.user_id == user_id).first()
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule not found"
        )
    db.delete(sched)
    db.commit()
    return {"message": "Successfully deleted schedule"}

from services.shared.models import TaskExecution

@app.post("/api/v1/analytics/graphql")
def graphql_endpoint(payload: GraphQLQuery, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    query = payload.query
    query_clean = "".join(query.split()).lower()
    
    data = {}
    
    if "dashboard" in query_clean:
        active_goals_count = db.query(Goal).filter(Goal.user_id == user_id, Goal.status == "active").count()
        completed_tasks_count = db.query(Task).filter(Task.user_id == user_id, Task.status == "done").count()
        data["dashboard"] = {
            "tasks_done": completed_tasks_count,
            "active_goals": active_goals_count,
            "llm_cost": 0.045
        }
        
    if "goalwithfullcontext" in query_clean:
        goal_id = None
        if payload.variables and "id" in payload.variables:
            goal_id = payload.variables["id"]
        else:
            import re
            match = re.search(r'id:\s*"([a-f0-9\-]+)"', query, re.IGNORECASE)
            if match:
                goal_id = match.group(1)
                
        if goal_id:
            try:
                g_id = UUID(str(goal_id))
                goal = db.query(Goal).filter(Goal.id == g_id, Goal.user_id == user_id).first()
                if goal:
                    projects = db.query(Project).filter(Project.goal_id == g_id, Project.user_id == user_id).all()
                    tasks = db.query(Task).filter(Task.goal_id == g_id, Task.user_id == user_id).all()
                    task_ids = [t.id for t in tasks]
                    executions = db.query(TaskExecution).filter(TaskExecution.task_id.in_(task_ids)).all() if task_ids else []
                    memories = db.query(Memory).filter(Memory.user_id == user_id).limit(5).all()
                    
                    data["goalWithFullContext"] = {
                        "goal": {
                            "id": str(goal.id),
                            "title": goal.title,
                            "status": goal.status,
                            "progress": goal.progress
                        },
                        "projects": [
                            {
                                "id": str(p.id),
                                "title": p.title,
                                "status": p.status
                            } for p in projects
                        ],
                        "tasks": [
                            {
                                "id": str(t.id),
                                "title": t.title,
                                "status": t.status,
                                "priority_score": t.priority_score
                            } for t in tasks
                        ],
                        "recentExecutions": [
                            {
                                "id": str(e.id),
                                "agent_type": e.agent_type,
                                "status": e.status
                            } for e in executions
                        ],
                        "relevantMemories": [
                            {
                                "id": str(m.id),
                                "content": m.content,
                                "importance": m.importance
                            } for m in memories
                        ],
                        "healthScore": 0.95,
                        "riskFlags": []
                    }
            except Exception as e:
                print(f"GraphQL Context Resolution Error: {e}")
                
    return {"data": data}
