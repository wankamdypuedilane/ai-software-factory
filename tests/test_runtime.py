from pathlib import Path

import pytest

from ai_factory.agent_result import (
    AgentArtifactRequest,
    AgentResult,
)
from ai_factory.providers import MockProvider, ModelProvider
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state


class RuntimeTestProvider(ModelProvider):
    def run(
        self,
        context,
    ) -> AgentResult:
        return AgentResult(
            status="COMPLETED",
            summary="Architecture completed.",
            artifact_requests=[
                AgentArtifactRequest(
                    path="knowledge/architecture/system.md",
                    purpose="Document the system architecture.",
                )
            ],
            handoff="developer",
        )

    def generate(
        self,
        prompt: str,
    ) -> str:
        return "# System Architecture\n\nGenerated architecture."


def test_run_next_agent_executes_selected_agent(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "COMPLETED",
                },
                "ux_ui": {
                    "status": "COMPLETED",
                },
                "architect": {
                    "status": "READY",
                },
                "developer": {
                    "status": "NOT_STARTED",
                },
                "qa": {
                    "status": "NOT_STARTED",
                },
                "security": {
                    "status": "NOT_STARTED",
                },
                "devops": {
                    "status": "NOT_STARTED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "architect": [],
                }
            },
        },
    )

    provider = RuntimeTestProvider()

    agent_name, output = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "architect"

    assert output.status == "COMPLETED"
    assert output.summary == "Architecture completed."

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    architect = updated_state["agents"]["architect"]

    assert architect["status"] == "REVIEW_REQUIRED"
    assert architect["last_result"]["status"] == "COMPLETED"
    assert (
        architect["last_result"]["summary"]
        == "Architecture completed."
    )
    assert architect["last_result"]["generated_artifacts"] == [
        "knowledge/architecture/system.md"
    ]

    generated_file = (
        tmp_path
        / "knowledge"
        / "architecture"
        / "system.md"
    )

    assert generated_file.exists()
    assert (
        generated_file.read_text(encoding="utf-8")
        == "# System Architecture\n\nGenerated architecture."
    )


def test_run_next_agent_rejects_when_no_agent_is_ready(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "agents": {
                "product": {
                    "status": "APPROVED",
                },
                "ux_ui": {
                    "status": "REVIEW_REQUIRED",
                },
                "architect": {
                    "status": "NOT_STARTED",
                },
                "developer": {
                    "status": "NOT_STARTED",
                },
                "qa": {
                    "status": "NOT_STARTED",
                },
                "security": {
                    "status": "NOT_STARTED",
                },
                "devops": {
                    "status": "NOT_STARTED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
        },
    )

    provider = MockProvider()

    with pytest.raises(
        ValueError,
        match="Execution blocked",
    ):
        run_next_agent(
            project_root=tmp_path,
            provider=provider,
        )


from ai_factory.cli import main


def test_cli_run_executes_next_agent(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "COMPLETED",
                },
                "ux_ui": {
                    "status": "COMPLETED",
                },
                "architect": {
                    "status": "READY",
                },
                "developer": {
                    "status": "NOT_STARTED",
                },
                "qa": {
                    "status": "NOT_STARTED",
                },
                "security": {
                    "status": "NOT_STARTED",
                },
                "devops": {
                    "status": "NOT_STARTED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "architect": [],
                }
            },
            "ai": {
                "provider": "mock",
                "model": None,
                "settings": {
                    "temperature": None,
                    "max_output_tokens": None,
                },
            },
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "run",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert "Agent: architect" in output
    assert "Status: COMPLETED" in output
    assert "Summary:" in output
    assert (
        "Mock execution completed for agent: architect"
        in output
    )
    assert "Handoff: none" in output


def test_run_next_agent_updates_design_gate_for_ux_ui(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "APPROVED",
                },
                "ux_ui": {
                    "status": "READY",
                },
                "architect": {
                    "status": "NOT_STARTED",
                },
                "developer": {
                    "status": "NOT_STARTED",
                },
                "qa": {
                    "status": "NOT_STARTED",
                },
                "security": {
                    "status": "NOT_STARTED",
                },
                "devops": {
                    "status": "NOT_STARTED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
            "design_gate": {
                "status": "NOT_STARTED",
                "groups": {},
                "external_blockers": [],
                "human_approval": False,
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "ux_ui": [],
                }
            },
        },
    )

    class UXUIRuntimeProvider(ModelProvider):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="UX/UI completed.",
                artifact_requests=[
                    AgentArtifactRequest(
                        path="design/ux-ui/user-flows.md",
                        purpose="Document user flows.",
                    ),
                    AgentArtifactRequest(
                        path="design/ux-ui/screen-specs.md",
                        purpose="Document screen specifications.",
                    ),
                ],
                handoff="architect",
            )

        def generate(self, prompt: str) -> str:
            return "# Generated UX/UI Artifact"

    provider = UXUIRuntimeProvider()

    agent_name, result = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "ux_ui"
    assert result.status == "COMPLETED"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert updated_state["agents"]["ux_ui"]["status"] == "REVIEW_REQUIRED"

    gate = updated_state["design_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["groups"]["deliverables"] == {
        "approved": 2,
        "total": 2,
    }
    assert gate["external_blockers"] == []
    assert gate["human_approval"] is False


def test_run_next_agent_updates_technology_gate_for_architect(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "APPROVED",
                },
                "ux_ui": {
                    "status": "APPROVED",
                },
                "architect": {
                    "status": "READY",
                },
                "developer": {
                    "status": "NOT_STARTED",
                },
                "qa": {
                    "status": "NOT_STARTED",
                },
                "security": {
                    "status": "NOT_STARTED",
                },
                "devops": {
                    "status": "NOT_STARTED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
            "technology_gate": {
                "status": "NOT_STARTED",
                "human_approval": False,
                "proposal": {},
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "technology": {
                "selection_mode": "recommend",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "architect": [],
                }
            },
        },
    )

    class ArchitectRuntimeProvider(ModelProvider):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Architecture completed.",
                metadata={
                    "technology_proposal": {
                        "components": [
                            {
                                "name": "frontend",
                                "technology": "React",
                                "rationale": "Suitable for the web UI.",
                            },
                            {
                                "name": "backend",
                                "technology": "Django",
                                "rationale": "Suitable for the monolith.",
                            },
                            {
                                "name": "database",
                                "technology": "PostgreSQL",
                                "rationale": "Relational persistence.",
                            },
                        ]
                    }
                },
                handoff="developer",
            )

        def generate(self, prompt: str) -> str:
            return "# Generated Architecture Artifact"

    provider = ArchitectRuntimeProvider()

    agent_name, result = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "architect"
    assert result.status == "COMPLETED"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["architect"]["status"]
        == "REVIEW_REQUIRED"
    )

    gate = updated_state["technology_gate"]

    assert gate["status"] == "REVIEW_REQUIRED"
    assert gate["human_approval"] is False
    assert gate["proposal"] == {
        "components": {
            "frontend": {
                "technology": "React",
                "rationale": "Suitable for the web UI.",
            },
            "backend": {
                "technology": "Django",
                "rationale": "Suitable for the monolith.",
            },
            "database": {
                "technology": "PostgreSQL",
                "rationale": "Relational persistence.",
            },
        }
    }
