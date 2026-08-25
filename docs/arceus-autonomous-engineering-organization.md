# Arceus Autonomous Software Engineering Organization

## Positioning

Arceus is not another AI coding assistant, IDE, or chat-based agent.

Arceus Code is the first product surface for an autonomous software engineering organization: a persistent AI engineering team that plans, builds, reviews, verifies, learns from evidence, and continuously improves every repository it works on.

The product promise:

```text
Open a repository
  -> Arceus loads its engineering memory
  -> Creates the right team
  -> Plans the mission
  -> Executes with evidence
  -> Reviews and verifies
  -> Offers rollback and PR
  -> Extracts lessons for the next mission
```

## Strategic Bet

Do not compete feature-for-feature with Cursor, Windsurf, Copilot, Claude Code, or Codex. Autocomplete, chat, and code editing are table stakes.

The durable differentiation is a living engineering organization:

- Repository Digital Twin
- Engineering Organization
- Organization Brain
- Continuous Learning
- Engineering Advisor
- Mission Replay
- AI CTO
- AI Academy
- Self-Evolving Standards
- Predictive Engineering

## Repository Digital Twin

Every repository should have a persistent engineering profile:

- architecture
- services
- dependencies
- coding style
- design patterns
- technical debt
- previous missions
- engineering decisions
- successful implementations
- known risks

When a repository is opened again, Arceus should show what it already knows before asking the user to repeat context.

## Engineering Organization

Arceus should not present agents as isolated chat tabs. It should present an organization:

```text
CEO / Mission Lead
  -> CTO / Architect
  -> Backend Team
  -> Frontend Team
  -> QA
  -> Security
  -> Performance
  -> Documentation
```

Each role has a reason, authority, responsibilities, model policy, tool policy, and reviewer boundary.

## Organization Brain

The Organization Brain is a governed knowledge graph containing lessons, patterns, engineering standards, architecture decisions, reusable workflows, review feedback, model/tool performance, and recovery knowledge.

Before each mission, Arceus retrieves similar missions and applies proven knowledge only when the evidence is verified and relevant.

Current implementation slice:

- API: `GET /api/v1/learning/organization-brain`
- Source: `backend/services/agent/arceus_runtime/learning/service.py`
- Route: `backend/services/agent/arceus_runtime/learning/routes.py`
- Uses existing durable records: missions, evidence, lesson proposals, performance observations, and participants.
- Produces: knowledge candidates, engineering standards, repository memory, agent skill profiles, dynamic scheduling hints, cross-agent review rules, knowledge graph nodes/edges, and CEO-agent recommendations.

## Continuous Learning

Every completed mission should produce a structured learning cycle:

```text
Mission evidence
  -> Reflection
  -> Knowledge extraction
  -> Validation
  -> Memory promotion
  -> Future mission improvement
```

Learning must not mean blindly trusting every previous answer. Accepted lessons need provenance, confidence, freshness, and verification.

## Engineering Advisor

Arceus should proactively recommend useful missions:

- brittle authentication module
- missing tests around payments
- rising build failures
- slow preview performance
- growing technical debt
- risky release gate
- repeated rollback causes

The advisor should explain evidence, confidence, impact, and expected cost.

## V1 Product Loop

The V1 loop remains:

```text
Download Arceus Code
  -> Sign in
  -> Open or clone a repository
  -> Analyze repository
  -> Choose or create a mission
  -> Review three strategies
  -> Approve one plan
  -> Watch Mission Control execute
  -> Review evidence and patch
  -> Safe apply or rollback
  -> Commit or prepare PR
  -> Store lessons
```

Nothing else should outrank making this loop boringly reliable.

## Product Language

Use:

- "Autonomous Software Engineering Organization"
- "AI engineering organization"
- "Repository Digital Twin"
- "Organization Brain"
- "Mission Control"
- "Evidence-based execution"
- "Continuous learning"

Avoid positioning Arceus as only:

- coding assistant
- AI IDE
- chatbot
- autocomplete
- wrapper around models
- generic agent

## Definition Of Strategic Success

Arceus is strategically on-track when:

1. A repository becomes easier to work on after every mission.
2. A second mission uses verified knowledge from the first mission.
3. Users can replay why a decision was made months later.
4. Reviewers can inspect evidence, not just generated prose.
5. The organization improves standards based on repeated successful outcomes.
6. The app proactively recommends the next high-value engineering mission.
