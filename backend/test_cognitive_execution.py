from pathlib import Path

from services.agent.cognitive_execution import CognitiveCompileRequest, RepositoryContext, compile_cognitive_mission
from services.agent.repository_analysis import RepositoryAnalyzeRequest, analyze_repository_path


def test_cognitive_compile_builds_goal_understanding_and_task_graph():
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample-repository"
    analysis = analyze_repository_path(RepositoryAnalyzeRequest(workspace_id="cognitive-fixture", root_path=str(fixture), force=True))

    result = compile_cognitive_mission(
        CognitiveCompileRequest(
            workspace_id="cognitive-fixture",
            goal="Implement Google OAuth login and verify it with tests",
            repository=RepositoryContext(
                repository_id=analysis["repository_id"],
                root_path=str(fixture),
                summary=analysis["summary"],
                languages=analysis["languages"],
                frameworks=analysis["frameworks"],
                package_managers=analysis["package_managers"],
                entry_points=analysis["entry_points"],
                services=analysis["services"],
                test_commands=analysis["test_commands"],
                database_usage=analysis["database_usage"],
                authentication=analysis["authentication"],
                architecture_style=analysis["architecture_style"],
            ),
        )
    )

    assert result.state == "AWAITING_APPROVAL"
    assert result.understanding.intent == "feature"
    assert result.understanding.domain == "authentication"
    assert "backend" in result.understanding.repository_scope
    assert result.understanding.requires_ui is True
    assert result.understanding.requires_tests is True
    assert result.dependency_graph["valid"] is True
    assert result.dependency_graph["topological_order"][0] == "repo_context"
    assert "approval_gate" in result.dependency_graph["topological_order"]
    assert any(task.task_key == "backend_changes" for task in result.tasks)
    assert any(task.task_key == "frontend_changes" for task in result.tasks)
    assert any(agent.role == "Backend Engineer" for agent in result.agents)
    assert any(package.citations for package in result.context_packages)
    assert result.report.rollback_available is True
    assert result.report.confidence >= 0.9
