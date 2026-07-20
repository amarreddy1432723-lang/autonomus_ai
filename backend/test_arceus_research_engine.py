from services.agent.arceus_runtime.research.service import (
    build_publication,
    build_research_project,
    design_experiment,
    evaluate_evidence,
    generate_hypotheses,
    score_innovation,
    synthesize_findings,
    uncertainty_model,
)


def test_research_project_creates_org_questions_hypotheses_and_uncertainty():
    project = build_research_project(
        {
            "title": "Reduce migration failures",
            "objective": "Reduce enterprise deployment failures during database schema migrations.",
            "domain": "software_engineering",
            "observations": ["Deployments frequently fail during migration rollout."],
            "success_metrics": ["migration_failure_rate"],
            "constraints": ["must preserve rollback"],
            "evidence_ids": ["ev_1"],
        }
    )

    assert project["status"] == "active"
    assert project["domain"] == "software_engineering"
    assert len(project["research_organization"]) >= 6
    assert len(project["initial_hypotheses"]) == 3
    assert project["uncertainty"]["confidence"] > 0.5
    assert "RESEARCH_PROJECT_CREATED" in project["events"]


def test_hypothesis_generation_creates_competing_testable_hypotheses():
    hypotheses = generate_hypotheses(
        {
            "observation": "Developers spend excessive time reviewing pull requests.",
            "research_goal": "Reduce pull request review time by 35 percent.",
            "domain": "software_engineering",
            "competing_count": 4,
        }
    )

    assert len(hypotheses) == 4
    assert {item["hypothesis_key"] for item in hypotheses} == {"H1", "H2", "H3", "H4"}
    assert all(item["primary_metric"] in {"time_to_completion", "success_rate"} for item in hypotheses)
    assert any(item["type"] == "simulation" for item in hypotheses)


def test_experiment_design_records_reproducibility_and_statistical_plan():
    experiment = design_experiment(
        {
            "hypothesis": "Progressive rollout with automatic rollback reduces migration failures.",
            "objective": "Measure migration failure rate reduction.",
            "metrics": ["migration_failure_rate", "rollback_success_rate"],
            "datasets": ["historical_deployments", "simulation_runs"],
        }
    )

    assert experiment["status"] == "designed"
    assert experiment["design"]["simulation_type"] == "architecture_simulation"
    assert experiment["reproducibility"]["reproducibility_score"] > 0.7
    assert experiment["statistical_plan"]["effect_size_required"] is True
    assert "EXPERIMENT_STARTED" in experiment["events"]


def test_evidence_evaluation_reports_strength_and_uncertainty():
    score = evaluate_evidence(
        [
            {"reliability": 0.9, "validity": 0.82, "reproducibility": 0.86, "novelty": 0.6, "impact": 0.88},
            {"reliability": 0.82, "validity": 0.78, "reproducibility": 0.8, "novelty": 0.65, "impact": 0.84},
        ]
    )

    assert score["confidence"] >= 0.8
    assert score["conclusion_strength"] in {"moderate", "strong"}


def test_findings_preserve_insufficient_evidence_without_overclaiming():
    findings = synthesize_findings(
        [
            {
                "id": "research_1",
                "title": "Migration rollout research",
                "content": {"title": "Migration rollout", "objective": "Reduce failures", "evidence": []},
            }
        ]
    )

    assert len(findings) == 1
    assert findings[0]["conclusion_strength"] == "insufficient_evidence"
    assert "additional_evidence_required" in findings[0]["uncertain_areas"]


def test_publication_builds_review_workflow_and_traceable_report():
    publication = build_publication(
        {
            "title": "Progressive migration rollout RFC",
            "publication_type": "engineering_rfc",
            "audience": "engineering",
            "findings": [{"title": "Progressive rollout reduced failure rate", "confidence": 0.84}],
            "evidence_ids": ["ev_1", "ev_2", "ev_3"],
            "require_human_review": True,
        }
    )

    assert publication["status"] == "needs_human_review"
    assert publication["report"]["uncertainty"] == "low"
    assert publication["review_workflow"][2]["status"] == "required"


def test_innovation_scoring_prioritizes_evidence_backed_business_value():
    score = score_innovation(
        {
            "title": "Novel deployment rollback workflow",
            "findings": [{"title": "failure rate improved with verified experiment evidence"}],
            "evidence_ids": ["ev_1", "ev_2", "ev_3"],
        }
    )

    assert score["priority_score"] >= 0.65
    assert score["scientific_confidence"] > 0.65
    assert score["business_value"] > 0.7


def test_uncertainty_model_separates_probable_and_unknown_areas():
    hypotheses = generate_hypotheses({"observation": "Failures happen", "research_goal": "Reduce failure rate", "competing_count": 2})
    uncertainty = uncertainty_model(hypotheses, [])

    assert uncertainty["probable_findings"]
    assert uncertainty["uncertain_areas"]
    assert "actual_effect_size" in uncertainty["unknown_questions"]
