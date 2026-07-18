"""Resource and budget manager."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ResourceBudget:
    token_budget: int
    cost_budget: float
    tool_calls: int
    model_calls: int
    tokens_used: int = 0
    cost_used: float = 0.0
    tool_calls_used: int = 0
    model_calls_used: int = 0

    def can_spend(self, *, tokens: int = 0, cost: float = 0.0, tool_calls: int = 0, model_calls: int = 0) -> bool:
        return (
            self.tokens_used + tokens <= self.token_budget
            and self.cost_used + cost <= self.cost_budget
            and self.tool_calls_used + tool_calls <= self.tool_calls
            and self.model_calls_used + model_calls <= self.model_calls
        )

    def spend(self, *, tokens: int = 0, cost: float = 0.0, tool_calls: int = 0, model_calls: int = 0) -> None:
        if not self.can_spend(tokens=tokens, cost=cost, tool_calls=tool_calls, model_calls=model_calls):
            raise ValueError("Resource budget exceeded")
        self.tokens_used += tokens
        self.cost_used += cost
        self.tool_calls_used += tool_calls
        self.model_calls_used += model_calls

    def summary(self) -> dict[str, float | int]:
        return {
            "token_budget": self.token_budget,
            "tokens_used": self.tokens_used,
            "remaining_tokens": self.token_budget - self.tokens_used,
            "cost_budget": self.cost_budget,
            "cost_used": self.cost_used,
            "remaining_cost": round(self.cost_budget - self.cost_used, 4),
            "tool_calls": self.tool_calls,
            "tool_calls_used": self.tool_calls_used,
            "model_calls": self.model_calls,
            "model_calls_used": self.model_calls_used,
        }

