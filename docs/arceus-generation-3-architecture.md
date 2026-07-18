# Arceus Generation 3 Architecture

Generation 3 turns Arceus from an AI-only engineering runtime into a multi-user human-AI engineering organization. Humans, AI agents, services, and external reviewers use the same organizational primitives: participants, tasks, decisions, artifacts, approvals, channels, policies, evidence, and event history.

No structural implementation should start until this document is reviewed.

## 1. Generation 2 Assessment

Generation 2 is a strong kernel for dynamic AI organizations: it has capability catalogs, specialist profiles, organization plans, project memory, lessons, performance records, and auditable event-backed mission runtime. The main gap is that humans are still outside the same operating model. Human approvals exist, but humans are not first-class participants with workload, capabilities, availability, role bindings, authority scope, and responsibility chains.

Recommended approach: extend the OS kernel with collaboration-domain modules instead of rewriting mission, task, artifact, policy, memory, and event code.

Alternatives: create a separate collaboration app, or force humans into agent records. Both are rejected. Separate systems split audit history. Treating humans as agents creates unsafe identity and execution assumptions.

Migration impact: existing missions continue to work with AI-only participants. New Generation 3 missions attach participants and memberships gradually.

Rollback strategy: keep Generation 3 tables/routes behind module boundaries and feature flags until the vertical slice passes.

## 2. Generation 3 Gap Analysis

Missing capabilities:

- Unified participant model for humans, AI agents, services, and external reviewers.
- Organization and project memberships with scoped roles.
- Department model with shared services and work orders.
- Hybrid RBAC/ABAC permission evaluation.
- Separation-of-duties enforcement across authors, reviewers, approvers, deployers, and secret holders.
- Collaboration channels, messages, mentions, presence, sessions, councils, notifications, and escalations.
- Multi-repository, environment, branch, and change-scope authority.
- Responsibility chain view for artifacts, decisions, code changes, deployments, and incidents.
- Durable membership, approval, handoff, and channel event replay.

## 3. Unified Participant Model

Use `Participant` as the identity and responsibility primitive.

Types:

- `human`
- `ai_agent`
- `service`
- `external_reviewer`

Core fields:

- `participant_id`
- `tenant_id`
- `organization_id`
- `participant_type`
- `display_name`
- `status`
- `capabilities`
- `authority_scope`
- `memory_scope`
- `tool_scope`
- `current_assignments`
- `performance_reference`
- `created_at`

Humans do not execute model calls. AI agents do not possess human identity, login state, or human approval authority unless policy explicitly grants a narrow approval role for low-risk internal actions.

Decision: one participant abstraction, participant-specific execution adapters.

Risk: over-generalization. Mitigation: keep execution methods separate.

## 4. Organizational Hierarchy

Canonical hierarchy:

```text
Tenant
  Organization
    Departments
      Persistent teams
      Human members
      AI specialist profiles
      Capabilities
      Policies
      Budgets
      Services
    Projects
      Repositories
      Environments
      Project members
      Project memory
      Missions
      Artifacts
    Cross-project services
      Security review
      Architecture review
      QA
      DevOps
      Compliance
      AI platform services
```

Departments provide reusable capability services. Projects request them through work orders instead of duplicating every specialist.

## 5. Role Taxonomy

Roles are scoped. There is no universal admin role.

Organization roles:

- Organization Owner
- Administrator
- Engineering Director
- Security Director
- Finance Administrator
- Auditor
- Member

Project roles:

- Project Owner
- Product Owner
- Technical Lead
- Engineer
- Reviewer
- Operator
- Observer

Mission roles:

- Mission Owner
- Mission Lead
- Specialist
- Domain Expert
- Reviewer
- Approver
- Observer

Task roles:

- Owner
- Contributor
- Reviewer
- Verifier
- Approver

Environment roles:

- Development Operator
- Staging Operator
- Production Operator
- Incident Responder

## 6. Permission And Authority Model

Use hybrid RBAC and ABAC. RBAC grants baseline authority. ABAC narrows or elevates decisions based on context.

Inputs:

- tenant, organization, department, project, mission
- participant and participant type
- roles and capabilities
- resource type and owner
- environment
- risk level
- data sensitivity
- action type
- approval status
- incident state
- budget authority
- time and location policy
- separation-of-duties conflicts

Decision shape:

```json
{
  "allowed": false,
  "decision": "deny",
  "reason_codes": [],
  "matched_policies": [],
  "required_approvers": [],
  "conditions": [],
  "expires_at": null
}
```

Authority categories:

`VIEW`, `COMMENT`, `PROPOSE`, `ASSIGN`, `MODIFY`, `EXECUTE_TOOL`, `REVIEW`, `VERIFY`, `APPROVE`, `DEPLOY`, `MANAGE_MEMBERS`, `MANAGE_POLICY`, `MANAGE_BUDGET`, `ACCESS_SECRET`, `RESPOND_TO_INCIDENT`, `DELETE`, `EXPORT`.

Sensitive decisions must emit audit events.

## 7. Separation-Of-Duties Matrix

Initial conflict rules:

| Responsibility | Cannot Solely Satisfy |
| --- | --- |
| Author | Approval for high-risk artifact |
| Implementer | Security review for own change |
| Production deployer | Release approval for same deployment |
| Billing admin | Financial configuration approval for own change |
| AI agent | Permission grant to itself |
| Project owner | Immutable audit modification |
| Security policy author | Final security policy approval |
| Data deletion requester | User-data deletion approval |
| External reviewer | Approval outside invitation scope |

Evaluation returns `allow`, `deny`, or `require_approval`.

## 8. Departments And Shared Services

Initial departments:

- Product
- Architecture
- Frontend
- Backend
- Data
- AI
- Security
- Quality Engineering
- Platform and DevOps
- Site Reliability
- Compliance
- Documentation

Department fields:

- `department_id`
- `tenant_id`
- `organization_id`
- `name`
- `type`
- `head_participant_id`
- `capabilities`
- `members`
- `policies`
- `budgets`
- `service_catalog`
- `status`

Shared service examples:

- Security: threat-model review, auth review, dependency review, incident response.
- Architecture: system review, data architecture review, integration review.
- QA: test strategy, regression verification, release validation.
- DevOps: preview deployment, release gate, rollback drill.

## 9. Multi-User Membership Model

Human member:

- organization roles
- department memberships
- project memberships
- capabilities
- authority bindings
- availability
- notification preferences
- status: `invited`, `active`, `suspended`, `removed`

Project membership:

- project roles
- repository access
- environment access
- secret access
- mission permissions
- approval authority
- expiration
- added by
- reason

Invitations expire. External reviewers receive minimum necessary time-bound access.

## 10. Human-AI Task Ownership Model

Tasks support human and AI ownership through participant IDs.

Task assignment considers:

- capability match
- authority
- availability
- workload
- independence requirements
- cost and deadline
- project preference
- historical performance
- need for human judgment
- deterministic execution needs

Tasks record:

- primary owner
- contributors
- reviewers
- verifiers
- approvers
- participant types
- ownership history
- handoff history
- required capabilities
- authority requirements
- blockers
- evidence
- communication channel

Policy may require accountable human ownership for production, financial, legal, or high-sensitivity work.

## 11. Collaboration Channel Architecture

Channels are shared by humans and AI.

Types:

- organization
- department
- project
- mission
- team
- task
- decision
- incident
- approval
- announcement

Messages are typed:

- human comment
- AI proposal
- automated system event
- tool result
- approval decision
- verification result
- review request
- evidence attachment

AI identity cannot impersonate humans. Mentions and notifications use participant IDs.

## 12. Session And Council Model

Sessions represent structured meetings or reviews. Councils represent decision bodies.

Session fields:

- agenda
- participants
- context artifacts
- decisions
- action items
- evidence
- recording/transcript reference when available

Council fields:

- scope
- membership
- authority categories
- quorum rules
- veto roles
- decision records

## 13. Approval Quorum Design

Approval policy defines:

- required roles
- required participant count
- independence constraints
- veto roles
- expiration
- invalidation triggers

Approval is invalidated when the approved artifact changes materially, evidence expires, scope changes, or policy changes.

Example: staging deployment requires Technical Lead plus QA. Production deployment requires Production Operator plus Security Reviewer plus Product Owner, unless emergency incident policy applies.

## 14. Repository And Change-Scope Model

Projects may contain multiple repositories.

Repository records include:

- provider
- owner/repo
- default branch
- access bindings
- protected branches
- policy references

Change scopes isolate work:

- mission ID
- task ID
- participant owner
- repository
- branch
- file/path scope
- environment target
- status

Work across repositories is traceable and cannot share permissions implicitly.

## 15. Environment Authority Model

Environments:

- development
- staging
- production
- preview
- sandbox

Each environment has independent authority:

- deploy
- read logs
- access secrets
- modify config
- run migrations
- rollback

Development access does not imply production access.

## 16. Secret Access Architecture

Secrets are references, not raw values.

Access flow:

1. Participant requests secret use for a task.
2. Policy evaluates scope, environment, risk, and approval state.
3. Broker issues time-limited credentials or injects secret into a controlled tool run.
4. Raw secret is never stored in events, prompts, artifacts, logs, or Sentry.
5. Access event is audited.

## 17. Policy Inheritance Model

Policy order:

1. Tenant baseline
2. Organization policy
3. Department policy
4. Project policy
5. Mission policy
6. Resource policy
7. Exception policy

Deny overrides allow. More restrictive environment policy wins. Exceptions are explicit, scoped, time-bound, and audited.

## 18. Policy Exception Workflow

States:

- requested
- reviewed
- approved
- active
- expired
- revoked
- rejected

Exception fields:

- requester
- policy target
- reason
- evidence
- risk
- expiration
- approvers
- compensating controls

Exceptions cannot outlive expiration and cannot disable immutable audit.

## 19. Portfolio Architecture

Portfolios group projects and initiatives.

Fields:

- portfolio owner
- projects
- dependencies
- roadmap
- shared capabilities
- risk posture
- costs
- delivery health
- recommendations

Use portfolio intelligence for cross-project risk and shared capability planning, not as a replacement for project authority.

## 20. Cross-Project Knowledge Model

Knowledge scopes:

- task
- mission
- project
- department
- organization
- tenant
- global

Promotion requires stronger trust:

- repeated use
- independent review
- applicability analysis
- redaction
- approval by authority

Confidential project details cannot be promoted into broader scopes without abstraction.

## 21. Responsibility-Chain Design

Every material artifact answers:

- proposed by
- authored by
- contributors
- reviewers
- verifiers
- approvers
- model used
- tool used
- policy decision
- evidence
- mission/task
- environment affected
- resulting changes

Responsibility chains are read models built from event history plus current artifact metadata.

## 22. Database Migration Plan

Phase tables:

1. Identity and membership:
   - `participants`
   - `human_members`
   - `participant_capabilities`
   - `role_bindings`
   - `authority_bindings`
   - `project_memberships`
   - `project_invitations`

2. Governance:
   - `permission_policies`
   - `policy_exceptions`
   - `approval_policies`
   - `approval_quorums`
   - `approval_votes`

3. Departments:
   - `departments`
   - `department_memberships`
   - `department_services`
   - `service_work_orders`

4. Collaboration:
   - `collaboration_channels`
   - `channel_members`
   - `channel_threads`
   - `channel_messages`
   - `mentions`
   - `notifications`
   - `notification_preferences`

5. Repository/environment:
   - `repositories`
   - `repository_access`
   - `repository_branches`
   - `change_scopes`
   - `environments`
   - `environment_access`
   - `secret_references`
   - `secret_access_requests`

6. Portfolio and responsibility:
   - `portfolios`
   - `portfolio_projects`
   - `portfolio_dependencies`
   - `cross_project_knowledge`
   - `responsibility_chains`
   - `participant_availability`
   - `participant_workloads`
   - `escalations`
   - `escalation_routes`

Every tenant-owned table includes `tenant_id`.

## 23. API Contract Changes

Add route modules by bounded context:

- `routes_organizations.py`
- `routes_departments.py`
- `routes_project_memberships.py`
- `routes_repositories.py`
- `routes_collaboration.py`
- `routes_tasks_collaboration.py`
- `routes_councils.py`
- `routes_approvals.py`
- `routes_policies.py`
- `routes_portfolios.py`
- `routes_notifications.py`
- `routes_escalations.py`

Mutations require:

- tenant scope
- idempotency key where retryable
- permission evaluation
- audit event

## 24. Frontend Information Architecture

Persistent workspaces:

- Organization Workspace: departments, members, AI specialists, policies, budgets, health.
- Team Workspace: participants, roles, availability, workload, missions, escalations.
- Project Workspace: members, repos, environments, missions, memory, decisions, risks, cost.
- Collaboration Workspace: channels, threads, mentions, proposals, reviews, notifications.
- Governance Workspace: roles, permissions, policy exceptions, approval rules, access, audit.
- Portfolio Workspace: projects, roadmap, dependencies, shared capabilities, risks, costs.
- Responsibility Chain: full provenance for any material artifact.

The same workspace contains humans and AI participants. Do not create a separate human chat product.

## 25. First Vertical Slice Implementation Plan

Scenario: three humans and five AI participants collaborate on a production-ready authentication improvement.

Phase 1:

- Create organization.
- Invite Product Owner, Backend Engineer, Technical Lead.
- Attach repository and development/staging/production environments.
- Create participants for Product Analyst, Authentication Specialist, Security Reviewer, QA Reviewer, DevOps Specialist.

Phase 2:

- Product Owner creates mission.
- Arceus generates hybrid team.
- Technical Lead approves architecture.

Phase 3:

- Human Backend Engineer owns one implementation task.
- AI Authentication Specialist owns another.
- Explicit handoff is possible in both directions.

Phase 4:

- Security and QA review both tasks.
- DevOps creates preview deployment.
- Technical Lead approves staging.
- Production deploy remains blocked without production authority.

Phase 5:

- Responsibility chains are visible.
- Approved authentication decision is stored as project memory.
- Later mission retrieves it.

## 26. Security Threat Model

Primary threats:

- cross-tenant access
- AI impersonating human
- forged approvals
- author self-approval
- stale approval after artifact change
- external reviewer overreach
- production secret exposure
- frontend-only permission enforcement
- notification spam leaking sensitive context
- policy exception abuse
- audit tampering

Controls:

- tenant ID on every entity
- backend permission checks
- participant type labels
- immutable event history
- approval invalidation
- scoped invitations
- secret broker
- redaction
- separation-of-duties graph
- audit on sensitive decisions

## 27. Testing Strategy

Unit:

- role resolution
- policy inheritance
- permission evaluation
- separation of duties
- approval quorum
- membership expiry
- work-order routing
- handoff acknowledgement
- environment and repository access
- notification filtering
- policy exception expiry

Integration:

- invite multiple users
- assign different project roles
- build hybrid organization
- human-owned and AI-owned tasks
- bidirectional handoff
- multi-person approval
- approval invalidation after artifact change
- department service request
- production access restriction
- cross-project knowledge reuse
- escalation resolution

Security:

- cross-tenant access blocked
- observer cannot modify
- AI cannot impersonate human
- AI cannot grant itself authority
- author cannot satisfy independent review
- expired invite cannot be accepted
- external reviewer cannot access unrelated files
- dev role cannot access production secrets
- policy exception cannot outlive expiration
- frontend-hidden action blocked in backend
- repository access denied
- quorum cannot be forged

End-to-end:

- create org, departments, users, project, repos, environments
- create hybrid mission
- assign humans and AI
- perform handoffs
- complete review council
- meet approval quorum
- generate preview deployment
- block unauthorized production deploy
- complete mission
- restart
- replay memberships, decisions, approvals, artifacts, chains

## 28. Rollback Plan

Technical rollback:

- feature flag Generation 3 route registration
- make migrations additive first
- keep old mission/task APIs functional
- avoid destructive schema changes
- backfill read models from events
- rebuild responsibility chains from events if derived tables fail

Operational rollback:

- disable collaboration routes
- preserve event log
- keep participant and membership records read-only
- revert frontend navigation to existing workspace

## 29. Estimated Implementation Sequence

1. Identity and memberships.
2. Permissions and authority.
3. Departments and shared services.
4. Unified collaboration.
5. Unified task ownership and handoffs.
6. Councils and approval quorums.
7. Repositories and environments.
8. Secrets and sensitive operations.
9. Portfolios and cross-project intelligence.
10. UI workspaces and full validation.

## Decision Records

### Unified Participant Model

Recommended: one participant abstraction with type-specific execution adapters.

Advantages: shared ownership, audit, channels, policy, and responsibility chain.

Disadvantages: requires careful naming so humans are not treated like model workers.

Risks: accidental authority leakage between participant types.

Reason selected: it satisfies the core principle that humans and AI operate in one organization.

Migration impact: AI specialists become participant records; existing mission assignments map to participant IDs.

Rollback: keep legacy assignment references until migration is complete.

### Hybrid RBAC/ABAC

Recommended: scoped roles plus contextual policy evaluation.

Alternatives: role-only RBAC or custom checks per route.

Advantages: enterprise governance without making small projects unusable.

Disadvantages: more policy surface to test.

Risks: policy complexity causing unexpected denies.

Reason selected: environment, sensitivity, risk, and separation-of-duties cannot be represented safely by role alone.

Migration impact: existing project role checks become policy inputs.

Rollback: default to stricter deny for new sensitive actions.

### Additive Database Migration

Recommended: additive tables and read models before replacing existing flows.

Alternatives: rewrite existing project/membership schema.

Advantages: safer deploy, lower rollback risk, preserves current product.

Disadvantages: temporary duplication.

Risks: sync drift during transition.

Reason selected: Generation 3 must preserve working Generation 1/2 behavior.

Rollback: disable new routes and leave old schema untouched.

### Responsibility Chains From Events

Recommended: derive chains from immutable events and artifact metadata.

Alternatives: store only denormalized chain rows.

Advantages: replayable, auditable, rebuildable.

Disadvantages: read model generation required.

Risks: missing event payloads create chain gaps.

Reason selected: "events remember" is a core OS rule.

Rollback: rebuild responsibility read models from event history.

