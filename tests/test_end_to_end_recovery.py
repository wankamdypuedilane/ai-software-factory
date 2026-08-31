from pathlib import Path

from ai_factory.approval_runtime import apply_approval
from ai_factory.project import initialize_project
from ai_factory.providers import MockProvider
from ai_factory.qa_result import QAResult
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state
from ai_factory.technology_gate import (
    approve_technology_gate,
)
from ai_factory.technology_selection import (
    apply_approved_technology_to_config,
)
from ai_factory.transitions import retry_agent


class FlakyQAProvider(MockProvider):
    """Mock provider whose first QA validation fails."""

    def __init__(self) -> None:
        self.qa_attempts = 0

    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        self.qa_attempts += 1

        if self.qa_attempts == 1:
            return QAResult(
                summary="Mock QA validation failed.",
                passed=False,
                defects=[],
                test_commands=[],
                blockers=[],
            )

        return QAResult(
            summary="Mock QA validation passed.",
            passed=True,
            defects=[],
            test_commands=[],
            blockers=[],
        )


def advance_project_to_qa(
    project_root: Path,
    provider: FlakyQAProvider,
) -> None:
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

    state = apply_approval(
        state,
        "development",
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
        state["agents"]["qa"]["status"]
        == "READY"
    )

    assert (
        state["project"]["phase"]
        == "qa"
    )


def test_factory_recovers_from_failed_qa_with_retry(
    tmp_path: Path,
) -> None:
    project_root = initialize_project(
        project_name="Recovery Test App",
        target_dir=tmp_path,
    )

    state_path = (
        project_root
        / ".factory"
        / "state.yaml"
    )

    provider = FlakyQAProvider()

    advance_project_to_qa(
        project_root=project_root,
        provider=provider,
    )

    # First QA attempt fails.
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "qa"
    assert provider.qa_attempts == 1

    state = load_state(
        state_path
    )

    assert (
        state["agents"]["qa"]["status"]
        == "FAILED"
    )

    assert (
        state["agents"]["security"]["status"]
        == "NOT_STARTED"
    )

    assert (
        state["qa_gate"]["status"]
        == "NOT_READY"
    )

    assert (
        state["agents"]["qa"][
            "last_result"
        ]["qa_passed"]
        is False
    )

    assert (
        state["project"]["phase"]
        == "qa"
    )

    # Human/operator retries QA.
    state = retry_agent(
        state,
        "qa",
    )

    save_state(
        state_path,
        state,
    )

    state = load_state(
        state_path
    )

    assert (
        state["agents"]["qa"]["status"]
        == "READY"
    )

    assert (
        state["project"]["phase"]
        == "qa"
    )

    # Second QA attempt succeeds.
    agent_name, _ = run_next_agent(
        project_root=project_root,
        provider=provider,
    )

    assert agent_name == "qa"
    assert provider.qa_attempts == 2

    state = load_state(
        state_path
    )

    assert (
        state["agents"]["qa"]["status"]
        == "REVIEW_REQUIRED"
    )

    assert (
        state["qa_gate"]["status"]
        == "READY_FOR_REVIEW"
    )

    assert (
        state["agents"]["qa"][
            "last_result"
        ]["qa_passed"]
        is True
    )

    # Human approves the recovered QA execution.
    state = apply_approval(
        state,
        "qa",
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
        final_state["agents"]["qa"]["status"]
        == "APPROVED"
    )

    assert (
        final_state["qa_gate"]["status"]
        == "APPROVED"
    )

    assert (
        final_state["qa_gate"][
            "human_approval"
        ]
        is True
    )

    assert (
        final_state["agents"]["security"]["status"]
        == "READY"
    )

    assert (
        final_state["project"]["phase"]
        == "security"
    )