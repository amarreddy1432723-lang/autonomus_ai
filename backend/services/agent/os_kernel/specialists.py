"""Generation 1 specialist capability definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id


SpecialistRole = Literal["product_analyst", "solution_architect", "implementation_engineer", "security_reviewer", "qa_reviewer"]


@dataclass(slots=True)
class SpecialistProfile:
    role: SpecialistRole
    display_name: str
    responsibilities: list[str]
    capabilities: list[str]
    authority: dict[str, bool]
    model_selection_policy: dict[str, Any] = field(default_factory=dict)
    profile_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "role": self.role,
            "display_name": self.display_name,
            "responsibilities": self.responsibilities,
            "capabilities": self.capabilities,
            "authority": self.authority,
            "model_selection_policy": self.model_selection_policy,
        }


def generation_one_specialists() -> list[SpecialistProfile]:
    return [
        SpecialistProfile(
            "product_analyst",
            "Product Analyst",
            [
                "Understand the user objective",
                "Extract requirements",
                "Identify target users",
                "Identify constraints",
                "Define success criteria",
                "Identify missing information",
                "Maintain requirement traceability",
            ],
            ["requirements_extraction", "constraint_detection", "success_criteria_definition"],
            {"can_execute_tools": False, "can_review": True, "can_approve_own_work": False},
        ),
        SpecialistProfile(
            "solution_architect",
            "Solution Architect",
            [
                "Analyze the project structure",
                "Generate solution options",
                "Compare trade-offs",
                "Design architecture",
                "Identify dependencies",
                "Create implementation plans",
                "Propose technical decisions",
            ],
            ["architecture_review", "implementation_planning", "dependency_analysis"],
            {"can_execute_tools": False, "can_review": True, "can_approve_own_work": False},
        ),
        SpecialistProfile(
            "implementation_engineer",
            "Implementation Engineer",
            [
                "Execute approved tasks",
                "Modify files only within allowed scope",
                "Generate implementation artifacts",
                "Record file changes",
                "Run permitted tools",
                "Submit work for review",
            ],
            ["scoped_file_write", "patch_generation", "test_execution"],
            {"can_execute_tools": True, "can_review": False, "can_approve_own_work": False},
        ),
        SpecialistProfile(
            "security_reviewer",
            "Security Reviewer",
            [
                "Review architecture and implementation",
                "Detect security risks",
                "Review authentication and authorization",
                "Review secrets handling",
                "Review dependencies and input validation",
                "Block unsafe changes when justified",
            ],
            ["security_review", "secret_handling_review", "dependency_risk_review"],
            {"can_execute_tools": False, "can_review": True, "can_block": True, "can_approve_own_work": False},
        ),
        SpecialistProfile(
            "qa_reviewer",
            "QA Reviewer",
            [
                "Verify acceptance criteria",
                "Review implementation quality",
                "Run tests and builds",
                "Identify regressions",
                "Validate evidence",
                "Approve or reject task completion",
            ],
            ["qa_review", "build_verification", "test_validation"],
            {"can_execute_tools": True, "can_review": True, "can_block": True, "can_approve_own_work": False},
        ),
    ]

