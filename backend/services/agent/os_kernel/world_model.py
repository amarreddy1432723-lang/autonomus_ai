"""World model and controlled memory for Arceus OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import clamp_score, new_id, utc_now


KnowledgeKind = Literal["FACT", "CLAIM", "ASSUMPTION", "PREDICTION", "DECISION", "PREFERENCE", "POLICY"]
VerificationStatus = Literal["PROPOSED", "UNVERIFIED", "VERIFIED", "APPROVED", "SUPERSEDED", "REJECTED", "ARCHIVED"]
KnowledgeScope = Literal["working", "task", "mission", "project", "organization", "global"]
Sensitivity = Literal["public", "internal", "private", "secret"]


@dataclass(slots=True)
class KnowledgeItem:
    tenant_id: str
    kind: KnowledgeKind
    content: str
    source: str
    author: str
    scope: KnowledgeScope
    confidence: float = 0.5
    verification_status: VerificationStatus = "PROPOSED"
    freshness: float = 1.0
    sensitivity: Sensitivity = "internal"
    relationships: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    item_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    @property
    def trusted(self) -> bool:
        return self.verification_status in {"VERIFIED", "APPROVED"} and self.kind in {"FACT", "DECISION", "POLICY", "PREFERENCE"}

    def score_for_retrieval(self, *, relevance: float, same_scope: bool, has_authority: bool) -> float:
        status_bonus = {
            "APPROVED": 0.24,
            "VERIFIED": 0.18,
            "UNVERIFIED": 0.02,
            "PROPOSED": 0.0,
            "SUPERSEDED": -0.25,
            "REJECTED": -0.5,
            "ARCHIVED": -0.2,
        }[self.verification_status]
        sensitivity_penalty = 0.0 if has_authority or self.sensitivity in {"public", "internal"} else 0.4
        scope_bonus = 0.12 if same_scope else 0.0
        return round(clamp_score(relevance + status_bonus + scope_bonus + (self.freshness * 0.1) - sensitivity_penalty), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "tenant_id": self.tenant_id,
            "kind": self.kind,
            "content": self.content,
            "source": self.source,
            "author": self.author,
            "scope": self.scope,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "trusted": self.trusted,
            "freshness": self.freshness,
            "sensitivity": self.sensitivity,
            "relationships": self.relationships,
            "superseded_by": self.superseded_by,
            "created_at": self.created_at,
        }


class WorldModel:
    def __init__(self) -> None:
        self.knowledge: dict[str, KnowledgeItem] = {}

    def write(self, item: KnowledgeItem) -> KnowledgeItem:
        self.knowledge[item.item_id] = item
        return item

    def approve(self, item_id: str) -> KnowledgeItem:
        item = self.knowledge[item_id]
        if item.verification_status not in {"VERIFIED", "UNVERIFIED", "PROPOSED"}:
            raise ValueError(f"Cannot approve knowledge in state {item.verification_status}")
        item.verification_status = "APPROVED"
        return item

    def retrieve(self, *, tenant_id: str, query_terms: list[str], scope: KnowledgeScope, has_secret_authority: bool = False, limit: int = 5) -> list[KnowledgeItem]:
        terms = {term.lower() for term in query_terms}
        scored: list[tuple[float, KnowledgeItem]] = []
        for item in self.knowledge.values():
            if item.tenant_id != tenant_id:
                continue
            if item.sensitivity == "secret" and not has_secret_authority:
                continue
            content_terms = item.content.lower()
            relevance = sum(1 for term in terms if term in content_terms) / max(1, len(terms))
            score = item.score_for_retrieval(relevance=relevance, same_scope=item.scope == scope, has_authority=has_secret_authority)
            if score > 0:
                scored.append((score, item))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

