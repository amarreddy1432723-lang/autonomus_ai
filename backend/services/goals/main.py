import jwt
from typing import List
from uuid import UUID
from datetime import datetime
from fastapi import FastAPI, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.models import Goal, Task, Approval, Schedule, Project, Memory
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware
from services.agent.planner import decompose_goal, validate_no_cycles
from services.agent.executor import execute_pending_tasks
from services.goals.config import settings
from services.goals.schemas import (
    GoalCreate, GoalResponse, TaskResponse, TaskUpdate, 
    ApprovalResponse, ApprovalResolve, ScheduleCreate, ScheduleResponse, GraphQLQuery
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
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

def get_current_user_id(
    authorization: str | None = Header(None), 
    x_user_id: str | None = Header(None, alias="x-user-id")
) -> UUID:
    # 1. Try Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id_str = payload.get("sub")
            if user_id_str:
                return UUID(user_id_str)
        except Exception:
            pass
            
    # 2. Try X-User-Id fallback
    if x_user_id:
        try:
            return UUID(x_user_id)
        except ValueError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials missing or invalid."
    )

@app.post("/api/v1/goals", response_model=GoalResponse, status_code=201)
def create_goal(goal_in: GoalCreate, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    # 1. Save Goal record
    goal = Goal(
        user_id=user_id,
        title=goal_in.title,
        description=goal_in.description,
        deadline=goal_in.deadline,
        status="active",
        progress=0.0
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    
    # 2. Decompose Goal using Planner Agent (pass deadline)
    decomposed_tasks = decompose_goal(user_id, goal.title, goal.description, goal.deadline)
    
    # Validate no circular dependencies
    if not validate_no_cycles(decomposed_tasks):
        db.delete(goal)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decomposed plan contains circular dependencies."
        )
    
    # 3. Create Task records
    saved_tasks = {}
    for task_data in decomposed_tasks:
        task = Task(
            goal_id=goal.id,
            user_id=user_id,
            title=task_data["title"],
            description=task_data["description"],
            assigned_agent=task_data["assigned_agent"],
            status="queued",
            priority_score=task_data["priority_score"],
            pert_estimate=task_data["pert_estimate"],
            optimistic_estimate=task_data["optimistic_estimate"],
            most_likely_estimate=task_data["most_likely_estimate"],
            pessimistic_estimate=task_data["pessimistic_estimate"]
        )
        db.add(task)
        saved_tasks[task_data["title"]] = (task, task_data)
        
    # Flush to generate IDs
    db.flush()
    
    # 4. Link dependencies in database
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
def list_goals(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(Goal).filter(Goal.user_id == user_id).all()

@app.get("/api/v1/goals/{id}", response_model=GoalResponse)
def get_goal(id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal

@app.get("/api/v1/tasks", response_model=List[TaskResponse])
def list_tasks(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(Task).filter(Task.user_id == user_id).all()

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
def list_approvals(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(Approval).filter(Approval.user_id == user_id).all()

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
def get_schedules(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(Schedule).filter(Schedule.user_id == user_id).all()

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
