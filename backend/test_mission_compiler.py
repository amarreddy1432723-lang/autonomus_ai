import pytest

from services.agent.os_kernel.mission_compiler import (
    MissionCompileRequest,
    MissionCompiler,
    MissionStateMachine,
)


def test_low_risk_admin_health_card_compiles_to_aml_and_execution_graph():
    compiled = MissionCompiler().compile(
        MissionCompileRequest(
            tenant_id="tenant",
            actor_id="founder",
            project_id="project-admin",
            objective="Add a health-status card to the admin interface using the existing health endpoint",
            repository_ids=["repo-web"],
            constraints=["Use the existing health endpoint", "Do not add new analytics charts"],
            desired_outcomes=["Admin users can see service health at a glance"],
            budget={"currency": "USD", "maximum": 10},
        )
    )

    payload = compiled.to_dict()
    aml = payload["aml"]
    graph = payload["definition"]["execution_graph"]

    assert compiled.state == "COMPILED"
    assert compiled.intent.execution_allowed is True
    assert aml["version"] == "1.0"
    assert aml["mission"]["project_id"] == "project-admin"
    assert "react_development" in aml["capabilities"]["required"]
    assert "frontend_build" in aml["verification"]["required"]
    assert any(node["node_type"] == "requirement" for node in graph["nodes"])
    assert any(node["node_type"] == "verification" for node in graph["nodes"])
    assert any(edge["edge_type"] == "VERIFIES" for edge in graph["edges"])
    assert payload["events"][0]["event_type"] == "MISSION_COMPILE_STARTED"
    assert payload["events"][1]["event_type"] == "MISSION_COMPILED"


def test_authentication_unknown_requires_clarification_before_execution():
    compiled = MissionCompiler().compile(
        MissionCompileRequest(
            tenant_id="tenant",
            actor_id="product-owner",
            project_id="project-auth",
            objective="Add Google OAuth login to the desktop and web applications",
            repository_ids=["repo-web", "repo-desktop"],
            constraints=[
                "Use the existing FastAPI authentication service",
                "Do not expose secrets in the desktop renderer",
            ],
            desired_outcomes=["Users can sign in through Google", "Existing sessions continue to work"],
        )
    )

    aml = compiled.definition.to_aml()

    assert compiled.state == "CLARIFICATION_REQUIRED"
    assert compiled.intent.execution_allowed is False
    assert compiled.definition.clarification_required is True
    assert "OAuth provider configuration and callback ownership must be confirmed." in compiled.definition.unknowns
    assert "authentication_review" in compiled.definition.required_capabilities
    assert "desktop_security" in compiled.definition.required_capabilities
    assert "authentication_changes" in aml["approvals"]["execution"]["required_for"]
    assert any(node.node_type == "human_action" for node in compiled.definition.execution_graph.nodes)
    assert compiled.events[1]["event_type"] == "MISSION_CLARIFICATION_REQUESTED"


def test_compiler_uses_assumptions_only_for_low_risk_unknown_free_work():
    compiled = MissionCompiler().compile(
        MissionCompileRequest(
            project_id="project",
            objective="Polish the admin interface spacing",
            constraints=["Keep the existing visual system"],
        )
    )

    assert compiled.definition.risk_profile.level == "low"
    assert compiled.definition.unknowns == []
    assert compiled.definition.assumptions == [
        "No material security, billing, deployment, or data-integrity unknowns detected."
    ]


def test_execution_graph_rejects_edges_to_missing_nodes():
    compiled = MissionCompiler().compile(MissionCompileRequest(project_id="project", objective="Add admin health card"))
    graph = compiled.definition.execution_graph
    graph.edges[0].source_id = "missing"

    with pytest.raises(ValueError):
        graph.validate()


def test_mission_state_machine_blocks_running_directly_to_completed():
    state_machine = MissionStateMachine()

    assert state_machine.transition("DRAFT", "COMPILING") == "COMPILING"
    assert state_machine.transition("COMPILING", "COMPILED") == "COMPILED"
    with pytest.raises(ValueError):
        state_machine.transition("RUNNING", "COMPLETED")


def test_empty_objective_is_rejected_before_compilation():
    with pytest.raises(ValueError):
        MissionCompiler().compile(MissionCompileRequest(project_id="project", objective="   "))

