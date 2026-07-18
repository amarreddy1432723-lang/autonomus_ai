from __future__ import annotations


class ApprovalPlanningStage:
    stage_key = "approval_planning"

    def run(self, payload: dict) -> dict:
        risk = payload["risk_planning"]["output"]["risk_profile"]
        approvals = [
            {
                "approval_key": "human_plan_approval",
                "subject": "execution_plan",
                "requires_human": True,
                "required_human_votes": 1,
            },
            {
                "approval_key": "independent_qa_review",
                "subject": "implementation_evidence",
                "requires_human": False,
                "required_reviewer_role": "qa_reviewer",
            },
        ]
        if risk.get("requires_security_review"):
            approvals.append(
                {
                    "approval_key": "security_review_when_risky",
                    "subject": "implementation_evidence",
                    "requires_human": False,
                    "required_reviewer_role": "security_reviewer",
                }
            )
        return {
            "status": "passed",
            "approval_gates": approvals,
            "warning_codes": [],
            "cost_usd": 0.0001,
        }
