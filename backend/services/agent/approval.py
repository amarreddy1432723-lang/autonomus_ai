from uuid import UUID
from sqlalchemy.orm import Session
from services.shared.models import UserProfile, Approval

def assess_task_risk(task_title: str, task_desc: str, db: Session = None, user_id: UUID = None) -> str:
    """
    Evaluates the risk/impact of a task using a 5-factor impact assessment matrix.
    Returns: "LOW" (auto-execution), "MED" (notify/confirm user), or "HIGH" (gated, requires approval).
    """
    title_lower = task_title.lower() if task_title else ""
    desc_lower = task_desc.lower() if task_desc else ""
    
    # 1. Reversibility (weight 0.35)
    # Default is fully reversible (5)
    reversibility = 5
    if any(k in title_lower or k in desc_lower for k in ["delete", "remove", "destroy", "send email", "email external", "pay", "purchase", "transaction", "push to main", "push to master"]):
        reversibility = 0
    elif any(k in title_lower or k in desc_lower for k in ["create file", "write file", "write code", "schedule event", "create calendar", "create branch", "push to feature", "sandbox"]):
        reversibility = 3

    # 2. External Impact (weight 0.25)
    # Default is internal state (5)
    external_impact = 5
    if any(k in title_lower or k in desc_lower for k in ["send email", "email external", "slack message", "send message", "share data"]):
        external_impact = 0
    elif any(k in title_lower or k in desc_lower for k in ["calendar", "email draft", "integration", "github"]):
        external_impact = 3

    # 3. Financial Consequence (weight 0.20)
    # Default is zero (5)
    financial = 5
    if any(k in title_lower or k in desc_lower for k in ["pay", "purchase", "transaction", "billing", "checkout", "subscription"]):
        financial = 0
    elif any(k in title_lower or k in desc_lower for k in ["signup", "sign up", "register account", "pricing"]):
        financial = 3

    # 4. Scope of Effect (weight 0.12)
    # Default is moderate (3)
    scope = 3
    if any(k in title_lower or k in desc_lower for k in ["delete database", "drop table", "push to main", "push to master", "production"]):
        scope = 0
    elif any(k in title_lower or k in desc_lower for k in ["memory", "update task status", "read file", "web search"]):
        scope = 5

    # 5. User Trust History (weight 0.08)
    trust_history = 0
    autonomy_level = "observer"
    
    if db and user_id:
        # Load user profile
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile:
            autonomy_level = profile.autonomy_level or "observer"
            
            # Check trust rules
            rules = profile.trust_rules or []
            if "auto_approve_search" in rules and ("search" in title_lower or "search" in desc_lower):
                trust_history = 5
            elif "auto_approve_calendar" in rules and ("calendar" in title_lower or "calendar" in desc_lower):
                trust_history = 5
                
        # Query past approvals
        approvals = db.query(Approval).filter(Approval.user_id == user_id).all()
        matching_approvals = []
        has_rejection = False
        for app in approvals:
            payload = app.payload or {}
            payload_title = payload.get("task_title", "").lower()
            if any(k in payload_title for k in ["search", "calendar", "email", "code", "file"]) and \
               any(k in title_lower for k in ["search", "calendar", "email", "code", "file"]):
                if app.status == "rejected":
                    has_rejection = True
                elif app.status == "approved":
                    matching_approvals.append(app)
                    
        if has_rejection:
            trust_history = 0
        elif len(matching_approvals) >= 10:
            trust_history = 5
        elif len(matching_approvals) >= 3:
            trust_history = 3

    # Calculate composite score
    composite_score = (
        0.35 * reversibility +
        0.25 * external_impact +
        0.20 * financial +
        0.12 * scope +
        0.08 * trust_history
    ) * 20.0  # Normalize to 0-100
    
    # Autonomy level thresholds adjustment
    threshold_auto = 80
    threshold_notify = 60
    threshold_confirm = 40
    
    if autonomy_level == "observer":
        threshold_auto = 90
        threshold_notify = 70
        threshold_confirm = 50
    elif autonomy_level == "partner":
        threshold_auto = 70
        threshold_notify = 50
        threshold_confirm = 30
    elif autonomy_level == "chief_of_staff":
        threshold_auto = 60
        threshold_notify = 40
        threshold_confirm = 20
        
    print(f"[Autonomy Assessor] Title: '{task_title}' -> Score: {composite_score:.1f} (Autonomy Level: {autonomy_level})")
    
    if composite_score >= threshold_auto:
        return "LOW"  # Fully autonomous
    elif composite_score >= threshold_confirm:
        return "MED"  # Notify / Confirm
    else:
        return "HIGH" # Full approval required
