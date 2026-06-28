from uuid import UUID
from datetime import datetime, date
from sqlalchemy.orm import Session
from services.shared.models import Goal, Task, Notification

def generate_morning_briefing(db: Session, user_id: UUID, available_hours: float = 8.0) -> str:
    """
    Implements the Daily Morning Briefing Algorithm:
    1. Selects the highest priority goal for the user.
    2. Filters and sorts queued tasks (giving precedence to critical path and today's deadlines).
    3. Allocates tasks to fit within available hours (accounting for a 20% buffer).
    4. Automatically writes a new Notification record and returns the briefing markdown.
    """
    # 1. Fetch active goals
    goals = db.query(Goal).filter(
        Goal.user_id == user_id,
        Goal.status == "in_progress"
    ).all()
    
    if not goals:
        goals = db.query(Goal).filter(Goal.user_id == user_id).all()
        
    if not goals:
        return "Good morning! No active goals found to plan today's focus. Create a goal to start!"
        
    # Calculate goal priority to select the focus goal
    # goal_priority = 0.40 * priority + 0.30 * urgency + 0.20 * momentum + 0.10 * strategic
    ranked_goals = []
    for g in goals:
        # User assigned priority (normally 1-5, lower numeric value is higher priority, default to 3)
        priority_val = 6.0 - (g.priority if g.priority else 3.0) # Inverted so higher value = higher priority
        
        # Urgency based on deadline proximity
        urgency = 0.0
        if g.deadline:
            days_left = (g.deadline - datetime.utcnow()).days
            if days_left <= 0:
                urgency = 5.0
            elif days_left <= 7:
                urgency = 4.0
            elif days_left <= 30:
                urgency = 2.0
            else:
                urgency = 1.0
                
        # Progress momentum
        momentum = 0.0
        tasks = db.query(Task).filter(Task.goal_id == g.id).all()
        if tasks:
            completed = sum(1 for t in tasks if t.status == "done")
            momentum = (completed / len(tasks)) * 5.0
            
        score = (0.40 * priority_val) + (0.30 * urgency) + (0.20 * momentum)
        ranked_goals.append((g, score))
        
    ranked_goals.sort(key=lambda x: x[1], reverse=True)
    focus_goal, focus_score = ranked_goals[0]
    
    # 2. Get queued tasks for this goal
    queued_tasks = db.query(Task).filter(
        Task.goal_id == focus_goal.id,
        Task.status == "queued"
    ).all()
    
    if not queued_tasks:
        # Fall back to any queued tasks for the user
        queued_tasks = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status == "queued"
        ).all()
        
    if not queued_tasks:
        return f"Good morning! Your focus goal for today is **{focus_goal.title}**. All tasks for this goal are currently completed or blocked."
        
    # Sort queued tasks:
    # 1. Tasks due today (forced to front)
    # 2. Critical path tasks (slack == 0)
    # 3. High composite priority score
    today_date = date.today()
    
    def get_task_sort_key(t):
        # High value = high precedence
        is_due_today = 1000 if t.due_date == today_date else 0
        
        # Extract critical path from native column
        is_critical = 500 if t.is_critical_path else 0
        
        # Priority score
        prio = t.priority_score or 0.0
        
        return is_due_today + is_critical + prio
        
    queued_tasks.sort(key=get_task_sort_key, reverse=True)
    
    # 3. Allocate tasks within available hours accounting for 20% buffer
    work_capacity = available_hours * 0.8  # e.g., 6.4 hours for an 8 hour day
    allocated_tasks = []
    stretch_tasks = []
    accumulated_hours = 0.0
    
    for t in queued_tasks:
        duration = t.est_hours_pert or 1.0
        if accumulated_hours + duration <= work_capacity:
            allocated_tasks.append(t)
            accumulated_hours += duration
        else:
            stretch_tasks.append(t)
            
    # 4. Generate standup briefing markdown
    briefing = f"Good morning! Here's your focus for today under goal **{focus_goal.title}** (estimated capacity: {work_capacity:.1f}h work / {available_hours - work_capacity:.1f}h buffer):\n\n"
    
    briefing += "### 🎯 Today's Core Focus\n"
    if allocated_tasks:
        for idx, t in enumerate(allocated_tasks, 1):
            is_crit = " *(Critical Path)*" if t.is_critical_path else ""
            briefing += f"{idx}. **{t.title}**{is_crit} - {t.est_hours_pert or 1.0}h\n"
            if t.description:
                briefing += f"   *Description: {t.description}*\n"
    else:
        briefing += "- No tasks fit in today's remaining time capacity.\n"
        
    if stretch_tasks:
        briefing += "\n### ⚡ Stretch Goals (If time permits)\n"
        for idx, t in enumerate(stretch_tasks[:3], 1):
            briefing += f"- **{t.title}** - {t.est_hours_pert or 1.0}h\n"
            
    briefing += "\n*I'll continue conducting background research and tracking dependency changes as we work today.*"
    
    # 5. Save briefing Notification to DB
    notification = Notification(
        user_id=user_id,
        title=f"Daily Focus: {focus_goal.title}",
        body=briefing,
        priority=1, # High priority standup notification
        channels=["in_app", "email"],
        status="sent"
    )
    db.add(notification)
    db.commit()
    
    print(f"[Proactive Engine] Compiled daily morning briefing standup notification for user {user_id}.")
    return briefing
