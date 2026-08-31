from pathlib import Path

from ai_factory.approval_runtime import apply_approval
from ai_factory.project import initialize_project
from ai_factory.provider_factory import create_provider
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state
from ai_factory.technology_gate import (
    approve_technology_gate,
)
from ai_factory.technology_selection import (
    apply_approved_technology_to_config,
)


def test_factory_full_mock_workflow_reaches_completed(
    tmp_path: Path,
) -> None:
    project_root = initialize_project(
        project_name="E2E Test App",
        target_dir=tmp_path,
    )

    state_path = (
        project_root
        / ".factory"
        / "state.yaml"
    )

    config_path = (
        project_root
        / ".factory"
        / "project.yaml"
    )

    config = load_state(
        config_path
    )

    provider = create_provider(
        config
    )

    # Product
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "product"

    state = load_state(
        state_path
    )

    state = apply_approval(
        state,
        "product_scope",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # UX/UI
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "ux_ui"

    state = load_state(
        state_path
    )

    assert (
        state["design_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    state = apply_approval(
        state,
        "design",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # Architect
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "architect"

    state = load_state(
        state_path
    )

    assert (
        state["technology_gate"]["status"]
        == "REVIEW_REQUIRED"
    )

    state = approve_technology_gate(
        state
    )

    config = load_state(
        config_path
    )

    config = apply_approved_technology_to_config(
        config=config,
        state=state,
    )

    save_state(
        config_path,
        config,
    )

    state = apply_approval(
        state,
        "architecture",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # Developer
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "developer"

    state = load_state(
        state_path
    )

    assert (
        state["development_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    state = apply_approval(
        state,
        "development",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # QA
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "qa"

    state = load_state(
        state_path
    )

    assert (
        state["qa_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    state = apply_approval(
        state,
        "qa",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # Security
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "security"

    state = load_state(
        state_path
    )

    assert (
        state["security_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    state = apply_approval(
        state,
        "security",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # DevOps
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "devops"

    state = load_state(
        state_path
    )

    assert (
        state["devops_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    state = apply_approval(
        state,
        "devops",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    # SRE
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "sre"

    state = load_state(
        state_path
    )

    assert (
        state["sre_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    state = apply_approval(
        state,
        "sre",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    state = load_state(
        state_path
    )

    assert (
        state["production_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    assert (
        state["project"]["phase"]
        == "production"
    )

    # Production
    state = apply_approval(
        state,
        "production_deployment",
        project_root=project_root,
    )

    save_state(
        state_path,
        state,
    )

    final_state = load_state(
        state_path
    )

    assert (
        final_state["project"]["phase"]
        == "completed"
    )

    assert (
        final_state["approvals"][
            "production_deployment"
        ]
        is True
    )

    assert (
        final_state["production_gate"]["status"]
        == "APPROVED"
    )

    assert (
        final_state["production_gate"][
            "human_approval"
        ]
        is True
    )

    for agent in final_state[
        "agents"
    ].values():
        assert agent["status"] == "APPROVED"

    assert (
        project_root
        / "src"
        / "mock_app.py"
    ).exists()

    expected_design_artifacts = [
        "accessibility-requirements.md",
        "design-system.md",
        "information-architecture.md",
        "responsive-rules.md",
        "screen-specs.md",
        "user-flows.md",
        "wireframes.md",
    ]

    for artifact_name in expected_design_artifacts:
        assert (
            project_root
            / "design"
            / "ux-ui"
            / artifact_name
        ).exists()