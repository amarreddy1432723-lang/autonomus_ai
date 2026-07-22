# Arceus v1.0 Product Roadmap

This roadmap freezes Arceus around one adoptable product loop:

```text
Download Arceus Code
  -> Sign in
  -> Open or clone a repository
  -> Ask for a feature or fix
  -> Review implementation plans
  -> Approve one plan
  -> Watch Mission Control execute
  -> Review evidence and patch
  -> Apply, rollback, commit, or prepare a PR
```

The product should not add more backend subsystems until this loop is reliable for real developers.

## Phase 1: Product Freeze

Goal: stabilize the runtime and stop expanding architecture.

Deliverables:

- No new runtime feature families.
- Scheduler, worker coordinator, recovery, and Mission Control bug fixes only.
- Verification scripts pass consistently.
- Database migrations and release gates are reviewed.
- Logging and error handling are standardized where user-facing errors appear.
- Dead code and obsolete feature flags are removed only when they are clearly unused.

Exit criteria:

- `.\scripts\verify-product-freeze.ps1` passes.
- `.\scripts\verify-core-loop.ps1` passes when local backend/frontend services are running.
- No critical runtime regression remains open.

## Phase 2: User Experience

Goal: make Arceus usable without technical guidance.

Required surfaces:

- Professional homepage.
- Feature walkthrough.
- Demo animation or video.
- Pricing page.
- Documentation.
- Download page.
- Desktop onboarding.

Desktop onboarding flow:

```text
Launch
  -> Sign in
  -> Choose repository
  -> Analyze repository
  -> Arceus creates plans
  -> Choose plan
  -> Mission begins
```

Mission Control must show:

- Live mission timeline.
- Agent avatars.
- Execution graph.
- Repository tree.
- Runtime metrics.
- Evidence explorer.
- Recovery center.
- Searchable logs.

## Phase 3: Repository Experience

Goal: make repository import feel automatic.

Supported inputs:

- Local folder.
- Git repository URL.
- GitHub clone.
- Existing workspace.

Auto-detect:

- Language.
- Framework.
- Build system.
- Package manager.
- Tests.
- CI.

Generated output:

- Repository summary.
- Architecture.
- Dependencies.
- Potential risks.
- Suggested improvements.

## Phase 4: Mission Experience

Users should create missions naturally:

- Add Google Authentication.
- Fix build failures.
- Improve performance.
- Add payment system.
- Refactor backend.
- Write tests.
- Improve accessibility.

Arceus should automatically:

- Analyze the mission.
- Estimate effort.
- Identify affected files.
- Generate multiple implementation strategies.

## Phase 5: Patch Review Experience

Patch review becomes the trust center:

- Side-by-side diff.
- Syntax highlighting.
- Risk score.
- Affected files.
- Estimated impact.
- AI explanation.
- Approve, reject, or request revision.

## Phase 6: Git Integration

Support:

- Branch creation.
- Commit creation.
- Commit message generation.
- Push with confirmation.
- Pull request preparation.
- Restore branch.

Rule: never push automatically.

## Phase 7: AI Quality

Improve intelligence over architecture.

Repository Analyst produces:

- Architecture overview.
- Dependency graph.
- Hotspots.
- Technical debt.

Planner produces:

- Implementation roadmap.
- Effort estimation.
- Risks.
- Milestones.

Backend Engineer produces:

- Clean patches.
- Tests.
- Documentation.

Reviewer checks:

- Style.
- Correctness.
- Security.
- Performance.
- Maintainability.

## Phase 8: Mission Analytics

Store for every mission:

- Duration.
- Success rate.
- Rollback count.
- Review iterations.
- Agent utilization.
- Verification results.

Dashboard:

- Total missions.
- Successful missions.
- Average completion time.
- Lines modified.
- Rollback percentage.
- Review percentage.
- Failure causes.

## Phase 9: Repository Testing Matrix

Test on:

- React.
- Next.js.
- FastAPI.
- Spring Boot.
- Django.
- Express.
- Vue.
- Angular.
- Flutter.
- Monorepo.

Measure:

- Completion.
- Verification.
- Rollback.
- Bugs introduced.

## Phase 10: Private Alpha

Invite 10 to 20 developers.

Collect:

- Crashes.
- Confusion.
- UX problems.
- Missing features.
- Reliability issues.

## Phase 11: Public Beta

Release:

- Website.
- Desktop installer.
- Documentation.
- Pricing.
- Community.
- Issue tracker.
- Roadmap.

## Phase 12: Version 1.0

Launch with:

- Windows, macOS, and Linux desktop.
- Repository analysis.
- Mission planning.
- Multi-agent execution.
- Patch review.
- Rollback.
- Mission Control.
- Clone, branch, commit, and PR preparation.
- Beautiful UI.
- Fast startup.
- Dark mode.
- Keyboard shortcuts.
- Notifications.
- Search.
- Billing, subscription plans, usage tracking, and organization support.

## Definition of Success

Arceus v1.0 succeeds when a new developer can complete the full loop confidently without help:

1. Download and install the desktop app.
2. Sign in.
3. Open or clone a repository.
4. Ask Arceus to implement a feature or fix.
5. Review multiple implementation plans.
6. Approve a plan.
7. Watch live multi-agent execution in Mission Control.
8. Review generated patch with explanations and evidence.
9. Apply changes or roll back.
10. Build, test, commit, and prepare a pull request.
