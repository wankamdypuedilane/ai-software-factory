from pathlib import Path

import pytest

from ai_factory.agent_result import (
    AgentArtifactRequest,
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.devops_result import (
    DevOpsChange,
    DevOpsResult,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.providers import (
    DevelopmentModelProvider,
    MockProvider,
    ModelProvider,
    QAProvider,
)
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state
from ai_factory.qa_result import (
    QADefect,
    QAResult,
)
from ai_factory.security_result import (
    SecurityFinding,
    SecurityResult,
)


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


class QARuntimeProvider(ModelProvider, QAProvider):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(
        self,
        context,
    ) -> AgentResult:
        return AgentResult(
            status="COMPLETED",
            summary="QA agent completed.",
        )

    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        self.prompts.append(
            prompt
        )

        return QAResult(
            summary="QA validation completed.",
            passed=True,
        )


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


def test_run_next_agent_executes_qa_validation(
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
                    "status": "COMPLETED",
                },
                "developer": {
                    "status": "COMPLETED",
                    "last_result": {
                        "implemented_files": [
                            "src/rides.py",
                        ],
                        "implementation_results": [
                            {
                                "task_id": "US-001",
                                "summary": "Ride creation implemented.",
                            }
                        ],
                    },
                },
                "qa": {
                    "status": "READY",
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
                    "qa": [],
                }
            },
        },
    )

    provider = QARuntimeProvider()

    agent_name, result = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "qa"
    assert result.summary == "QA agent completed."
    assert len(provider.prompts) == 1
    assert "# QA Validation" in provider.prompts[0]
    assert "src/rides.py" in provider.prompts[0]

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    qa_last_result = updated_state["agents"]["qa"]["last_result"]

    assert qa_last_result["qa_summary"] == (
        "QA validation completed."
    )
    assert qa_last_result["qa_model_passed"] is True
    assert qa_last_result["qa_passed"] is True
    assert qa_last_result["qa_defects"] == []
    assert qa_last_result["qa_blockers"] == []
    assert qa_last_result["qa_test_results"] == []


def test_run_next_agent_requires_qa_capable_provider(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "READY"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "qa_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "qa": [],
                }
            },
        },
    )

    class RunOnlyProvider(ModelProvider):
        def run(
            self,
            context,
        ) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="QA orchestration completed.",
            )

    provider = RunOnlyProvider()

    with pytest.raises(
        ValueError,
        match="QA-capable provider",
    ):
        run_next_agent(
            project_root=tmp_path,
            provider=provider,
        )


def test_run_next_agent_persists_qa_execution(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    test_file = (
        tmp_path
        / "tests"
        / "test_qa_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_qa_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {
                    "status": "APPROVED",
                    "last_result": {
                        "implemented_files": [
                            "src/app.py",
                        ],
                        "implementation_results": [
                            {
                                "task_id": "US-001",
                                "summary": "Implemented.",
                            }
                        ],
                    },
                },
                "qa": {"status": "READY"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "qa_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "qa": [],
                }
            },
        },
    )

    class QAExecutionProvider(DevelopmentModelProvider):
        def run(
            self,
            context,
        ) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="QA orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            return QAResult(
                summary="QA validation completed.",
                passed=False,
                defects=[
                    QADefect(
                        id="QA-001",
                        title="Minor issue",
                        severity="Low",
                        related_story="US-001",
                        expected="Expected behavior.",
                        actual="Actual behavior.",
                    )
                ],
                test_commands=[
                    "python -m pytest tests/test_qa_sample.py -q",
                ],
            )

    provider = QAExecutionProvider()

    agent_name, _ = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "qa"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    qa_last_result = updated_state[
        "agents"
    ]["qa"]["last_result"]

    assert qa_last_result["qa_summary"] == (
        "QA validation completed."
    )

    assert qa_last_result["qa_model_passed"] is False
    assert qa_last_result["qa_passed"] is False

    assert qa_last_result["qa_defects"] == [
        {
            "id": "QA-001",
            "title": "Minor issue",
            "severity": "Low",
            "related_story": "US-001",
            "expected": "Expected behavior.",
            "actual": "Actual behavior.",
        }
    ]

    assert qa_last_result["qa_blockers"] == []

    assert len(
        qa_last_result["qa_test_results"]
    ) == 1

    assert (
        qa_last_result["qa_test_results"][0]["passed"]
        is True
    )

    assert updated_state["agents"]["qa"]["status"] == "FAILED"

    qa_gate = updated_state["qa_gate"]

    assert qa_gate["status"] == "NOT_READY"
    assert "QA validation did not pass." in qa_gate["reasons"]
    assert qa_gate["human_approval"] is False


def test_run_next_agent_marks_qa_blocked_when_qa_has_blockers(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {"name": "Test Project"},
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "READY"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "qa_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "qa": [],
                }
            },
        },
    )

    class BlockingQAProvider(DevelopmentModelProvider):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="QA orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            return QAResult(
                summary="QA blocked.",
                passed=True,
                blockers=[
                    "Required test environment is unavailable.",
                ],
            )

    run_next_agent(
        project_root=tmp_path,
        provider=BlockingQAProvider(),
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert updated_state["agents"]["qa"]["status"] == "BLOCKED"


def test_run_next_agent_marks_qa_review_required_when_validation_passes(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {"name": "Test Project"},
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "READY"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "qa_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "qa": [],
                }
            },
        },
    )

    class PassingQAProvider(DevelopmentModelProvider):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="QA orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            return QAResult(
                summary="QA passed.",
                passed=True,
            )

    run_next_agent(
        project_root=tmp_path,
        provider=PassingQAProvider(),
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["qa"]["status"]
        == "REVIEW_REQUIRED"
    )

    qa_gate = updated_state["qa_gate"]

    assert qa_gate["status"] == "READY_FOR_REVIEW"
    assert qa_gate["reasons"] == []
    assert qa_gate["human_approval"] is False


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


def test_run_next_agent_executes_developer_implementation_batch(
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
                    "status": "APPROVED",
                },
                "developer": {
                    "status": "READY",
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
            "development_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {
                    "backend": {
                        "technology": "Django",
                        "rationale": "Test backend.",
                    }
                },
            },
            "context": {
                "agents": {
                    "developer": [],
                }
            },
        },
    )

    class DeveloperRuntimeProvider(DevelopmentModelProvider):
        def __init__(self) -> None:
            self.implementation_index = 0

        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Implementation planned.",
                implementation_requests=[
                    AgentImplementationRequest(
                        id="US-001",
                        title="Authentication",
                        purpose="Implement authentication.",
                    ),
                    AgentImplementationRequest(
                        id="US-002",
                        title="Ride creation",
                        purpose="Implement ride creation.",
                    ),
                ],
                handoff="qa",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            self.implementation_index += 1

            if self.implementation_index == 1:
                return ImplementationResult(
                    task_id="US-001",
                    summary="Authentication implemented.",
                    files=[
                        ImplementationFileChange(
                            path="src/auth.py",
                            content="# auth",
                        ),
                        ImplementationFileChange(
                            path="tests/test_auth.py",
                            content=(
                                "def test_auth():\n"
                                "    assert True\n"
                            ),
                        ),
                    ],
                    tests=[
                        "python -m pytest tests/test_auth.py -q",
                    ],
                )

            return ImplementationResult(
                task_id="US-002",
                summary="Ride creation implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/rides.py",
                        content="# rides",
                    ),
                    ImplementationFileChange(
                        path="tests/test_rides.py",
                        content=(
                            "def test_rides():\n"
                            "    assert True\n"
                        ),
                    ),
                ],
                tests=[
                    "python -m pytest tests/test_rides.py -q",
                ],
            )

    provider = DeveloperRuntimeProvider()

    agent_name, result = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "developer"
    assert result.status == "COMPLETED"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    development_gate = updated_state[
        "development_gate"
    ]

    assert (
        development_gate["status"]
        == "READY_FOR_REVIEW"
    )
    assert development_gate["reasons"] == []
    assert (
        development_gate["human_approval"]
        is False
    )

    developer = updated_state["agents"]["developer"]

    assert developer["status"] == "REVIEW_REQUIRED"

    last_result = developer["last_result"]

    assert len(
        last_result["implementation_results"]
    ) == 2

    assert last_result["implementation_results"][0][
        "task_id"
    ] == "US-001"

    assert last_result["implementation_results"][1][
        "task_id"
    ] == "US-002"

    assert last_result["implemented_files"] == [
        "src/auth.py",
        "tests/test_auth.py",
        "src/rides.py",
        "tests/test_rides.py",
    ]

    assert (
        last_result["implementation_blocked"]
        is False
    )
    assert last_result["implementation_blockers"] == []
    assert last_result["resume_from"] is None
    assert len(last_result["test_results"]) == 2
    assert all(
        item["passed"]
        for item in last_result["test_results"]
    )

    assert (
        tmp_path / "src" / "auth.py"
    ).exists()

    assert (
        tmp_path / "src" / "rides.py"
    ).exists()


def test_run_next_agent_blocks_developer_when_implementation_batch_blocks(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "READY"},
                "qa": {"status": "NOT_STARTED"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "developer": [],
                }
            },
        },
    )

    class BlockingDeveloperProvider(DevelopmentModelProvider):
        def __init__(self) -> None:
            self.implementation_index = 0

        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Implementation planned.",
                implementation_requests=[
                    AgentImplementationRequest(
                        id="US-001",
                        title="Authentication",
                        purpose="Implement authentication.",
                    ),
                    AgentImplementationRequest(
                        id="US-002",
                        title="Ride creation",
                        purpose="Implement ride creation.",
                    ),
                ],
                handoff="qa",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            self.implementation_index += 1

            if self.implementation_index == 1:
                return ImplementationResult(
                    task_id="US-001",
                    summary="Implementation blocked.",
                    blockers=[
                        "Authentication requirement is ambiguous.",
                    ],
                )

            return ImplementationResult(
                task_id="US-002",
                summary="Should not execute.",
            )

    provider = BlockingDeveloperProvider()

    agent_name, result = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "developer"
    assert result.status == "COMPLETED"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    developer = updated_state["agents"]["developer"]

    assert developer["status"] == "BLOCKED"

    last_result = developer["last_result"]

    assert last_result["implementation_blocked"] is True
    assert last_result["resume_from"] == "US-001"
    assert last_result["implementation_blockers"] == [
        {
            "task_id": "US-001",
            "blockers": [
                "Authentication requirement is ambiguous.",
            ],
        }
    ]
    assert len(last_result["implementation_results"]) == 1
    assert (
        last_result["implementation_results"][0]["task_id"]
        == "US-001"
    )

    assert provider.implementation_index == 1


def test_run_next_agent_skips_previously_completed_developer_tasks(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {
                    "status": "READY",
                    "last_result": {
                        "implementation_results": [
                            {
                                "task_id": "US-001",
                                "summary": "Authentication implemented.",
                                "tests": [],
                                "blockers": [],
                                "files": [
                                    "src/auth.py",
                                ],
                            },
                            {
                                "task_id": "US-002",
                                "summary": "Blocked.",
                                "tests": [],
                                "blockers": [
                                    "Requirement is ambiguous.",
                                ],
                                "files": [],
                            },
                        ],
                        "implemented_files": [
                            "src/auth.py",
                        ],
                    },
                },
                "qa": {"status": "NOT_STARTED"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "developer": [],
                }
            },
        },
    )

    class ResumeDeveloperProvider(DevelopmentModelProvider):
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Implementation replanned.",
                implementation_requests=[
                    AgentImplementationRequest(
                        id="US-001",
                        title="Authentication",
                        purpose="Implement authentication.",
                    ),
                    AgentImplementationRequest(
                        id="US-002",
                        title="Ride creation",
                        purpose="Implement ride creation.",
                    ),
                    AgentImplementationRequest(
                        id="US-003",
                        title="Ride completion",
                        purpose="Implement ride completion.",
                    ),
                ],
                handoff="qa",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            self.prompts.append(prompt)

            if len(self.prompts) == 1:
                return ImplementationResult(
                    task_id="US-002",
                    summary="Ride creation implemented.",
                    files=[
                        ImplementationFileChange(
                            path="src/rides.py",
                            content="# rides",
                        )
                    ],
                )

            return ImplementationResult(
                task_id="US-003",
                summary="Ride completion implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/completion.py",
                        content="# completion",
                    )
                ],
            )

    provider = ResumeDeveloperProvider()

    agent_name, _ = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    developer = updated_state["agents"]["developer"]
    last_result = developer["last_result"]

    history = last_result["implementation_results"]

    assert last_result["implemented_files"] == [
        "src/auth.py",
        "src/rides.py",
        "src/completion.py",
    ]

    assert agent_name == "developer"

    assert len(provider.prompts) == 2

    assert "Task ID: US-001" not in provider.prompts[0]
    assert "Task ID: US-002" in provider.prompts[0]
    assert "Task ID: US-003" in provider.prompts[1]

    assert [
        item["task_id"]
        for item in history
    ] == [
        "US-001",
        "US-002",
        "US-003",
    ]

    assert history[0]["summary"] == (
        "Authentication implemented."
    )

    assert history[1]["summary"] == (
        "Ride creation implemented."
    )

    assert history[1]["blockers"] == []

    assert history[2]["summary"] == (
        "Ride completion implemented."
    )


def test_run_next_agent_marks_developer_failed_when_tests_fail(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "READY"},
                "qa": {"status": "NOT_STARTED"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "development_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "developer": [],
                }
            },
        },
    )

    class FailingDeveloperProvider(DevelopmentModelProvider):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Implementation planned.",
                implementation_requests=[
                    AgentImplementationRequest(
                        id="US-001",
                        title="Authentication",
                        purpose="Implement authentication.",
                    ),
                    AgentImplementationRequest(
                        id="US-002",
                        title="Ride creation",
                        purpose="Implement ride creation.",
                    ),
                ],
                handoff="qa",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            return ImplementationResult(
                task_id="US-001",
                summary="Authentication implemented.",
                files=[
                    ImplementationFileChange(
                        path="tests/test_auth.py",
                        content=(
                            "def test_auth():\n"
                            "    assert False\n"
                        ),
                    )
                ],
                tests=[
                    "python -m pytest tests/test_auth.py -q",
                ],
            )

    provider = FailingDeveloperProvider()

    agent_name, result = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "developer"
    assert result.status == "COMPLETED"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    development_gate = updated_state[
        "development_gate"
    ]

    assert development_gate["status"] == "NOT_READY"
    assert development_gate["reasons"] == [
        "Developer implementation tests failed."
    ]
    assert (
        development_gate["human_approval"]
        is False
    )

    developer = updated_state["agents"]["developer"]

    assert developer["status"] == "FAILED"

    last_result = developer["last_result"]

    assert last_result["implementation_test_failed"] is True
    assert last_result["failed_task_id"] == "US-001"
    assert len(last_result["test_results"]) == 1

    test_result = last_result["test_results"][0]

    assert (
        test_result["command"]
        == "python -m pytest tests/test_auth.py -q"
    )

    assert test_result["returncode"] != 0
    assert test_result["passed"] is False
    assert isinstance(test_result["stdout"], str)
    assert isinstance(test_result["stderr"], str)
    assert last_result["implementation_blocked"] is False

    assert len(
        last_result["implementation_results"]
    ) == 1


def test_run_next_agent_uses_retry_context_for_failed_developer(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {
                    "status": "READY",
                    "last_result": {
                        "failed_task_id": "US-002",
                        "implementation_requests": [
                            {
                                "id": "US-001",
                                "title": "Authentication",
                                "purpose": "Implement authentication.",
                            },
                            {
                                "id": "US-002",
                                "title": "Ride creation",
                                "purpose": "Implement ride creation.",
                            },
                            {
                                "id": "US-003",
                                "title": "Ride completion",
                                "purpose": "Implement ride completion.",
                            },
                        ],
                        "implementation_results": [
                            {
                                "task_id": "US-001",
                                "summary": "Authentication implemented.",
                                "tests": [],
                                "blockers": [],
                                "files": [
                                    "src/auth.py",
                                ],
                            },
                            {
                                "task_id": "US-002",
                                "summary": "Ride creation failed.",
                                "tests": [
                                    "python -m pytest tests/test_rides.py -q",
                                ],
                                "blockers": [],
                                "files": [
                                    "src/rides.py",
                                ],
                            },
                        ],
                        "implemented_files": [
                            "src/auth.py",
                            "src/rides.py",
                        ],
                        "test_results": [
                            {
                                "command": (
                                    "python -m pytest "
                                    "tests/test_rides.py -q"
                                ),
                                "returncode": 1,
                                "passed": False,
                                "stdout": "1 failed",
                                "stderr": "AssertionError",
                            }
                        ],
                    },
                },
                "qa": {"status": "NOT_STARTED"},
                "security": {"status": "NOT_STARTED"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "developer": [],
                }
            },
        },
    )

    class RetryRuntimeProvider(DevelopmentModelProvider):
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Implementation replanned.",
                implementation_requests=[
                    AgentImplementationRequest(
                        id="US-001",
                        title="Authentication",
                        purpose="Implement authentication.",
                    ),
                    AgentImplementationRequest(
                        id="US-002",
                        title="Ride creation",
                        purpose="Implement ride creation.",
                    ),
                    AgentImplementationRequest(
                        id="US-003",
                        title="Ride completion",
                        purpose="Implement ride completion.",
                    ),
                ],
                handoff="qa",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            self.prompts.append(prompt)

            if len(self.prompts) == 1:
                return ImplementationResult(
                    task_id="US-002",
                    summary="Ride creation fixed.",
                )

            return ImplementationResult(
                task_id="US-003",
                summary="Ride completion implemented.",
            )

    provider = RetryRuntimeProvider()

    agent_name, _ = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    developer = updated_state["agents"]["developer"]
    last_result = developer["last_result"]

    assert last_result["implementation_test_failed"] is False
    assert last_result["failed_task_id"] is None
    assert last_result["resume_from"] is None
    assert last_result["test_results"] == []
    assert developer["status"] == "REVIEW_REQUIRED"

    assert agent_name == "developer"
    assert len(provider.prompts) == 2

    assert "Task ID: US-001" not in provider.prompts[0]

    assert "Task ID: US-002" in provider.prompts[0]
    assert "## Previous Test Failures" in provider.prompts[0]
    assert "AssertionError" in provider.prompts[0]

    assert "Task ID: US-003" in provider.prompts[1]
    assert "## Previous Test Failures" not in provider.prompts[1]


def test_run_next_agent_requires_security_capable_provider(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "READY"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "security": [],
                }
            },
        },
    )

    class RunOnlyProvider(ModelProvider):
        def run(
            self,
            context,
        ) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Security orchestration completed.",
            )

    provider = RunOnlyProvider()

    with pytest.raises(
        ValueError,
        match="Security-capable provider",
    ):
        run_next_agent(
            project_root=tmp_path,
            provider=provider,
        )


def test_run_next_agent_persists_security_execution(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    test_file = (
        tmp_path
        / "tests"
        / "test_security_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_security_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {
                    "status": "APPROVED",
                    "last_result": {
                        "implemented_files": [
                            "src/auth.py",
                        ],
                    },
                },
                "qa": {
                    "status": "APPROVED",
                    "last_result": {
                        "qa_passed": True,
                        "qa_defects": [],
                    },
                },
                "security": {"status": "READY"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "security_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "security": [],
                }
            },
        },
    )

    class SecurityExecutionProvider(
        DevelopmentModelProvider
    ):
        def run(
            self,
            context,
        ) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Security orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            raise AssertionError(
                "QA validation should not run."
            )

        def validate_security(
            self,
            prompt: str,
        ) -> SecurityResult:
            return SecurityResult(
                summary="Security validation completed.",
                passed=False,
                findings=[
                    SecurityFinding(
                        id="SEC-001",
                        title="Hard-coded secret detected",
                        severity="High",
                        affected_component="backend",
                        description=(
                            "A secret is committed in source code."
                        ),
                        impact="Credential exposure.",
                        evidence="src/config.py",
                        recommended_remediation=(
                            "Move the secret to environment variables."
                        ),
                        priority="P1",
                        status="OPEN",
                    )
                ],
                test_commands=[
                    "python -m pytest "
                    "tests/test_security_sample.py -q",
                ],
            )

    provider = SecurityExecutionProvider()

    agent_name, _ = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "security"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["security"]["status"]
        == "FAILED"
    )

    security_gate = updated_state[
        "security_gate"
    ]

    assert security_gate["status"] == "NOT_READY"

    assert (
        "Security validation did not pass."
        in security_gate["reasons"]
    )

    assert (
        security_gate["human_approval"]
        is False
    )

    security_last_result = updated_state[
        "agents"
    ]["security"]["last_result"]

    assert security_last_result[
        "security_summary"
    ] == "Security validation completed."

    assert security_last_result[
        "security_model_passed"
    ] is False

    assert security_last_result[
        "security_passed"
    ] is False

    assert security_last_result[
        "security_findings"
    ] == [
        {
            "id": "SEC-001",
            "title": "Hard-coded secret detected",
            "severity": "High",
            "affected_component": "backend",
            "description": (
                "A secret is committed in source code."
            ),
            "impact": "Credential exposure.",
            "evidence": "src/config.py",
            "recommended_remediation": (
                "Move the secret to environment variables."
            ),
            "priority": "P1",
            "status": "OPEN",
        }
    ]

    assert security_last_result[
        "security_blockers"
    ] == []

    assert len(
        security_last_result[
            "security_test_results"
        ]
    ) == 1

    assert security_last_result[
        "security_test_results"
    ][0]["passed"] is True


def test_run_next_agent_marks_security_blocked_when_blockers_exist(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {"name": "Test Project"},
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "READY"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "security": [],
                }
            },
        },
    )

    class BlockingSecurityProvider(
        DevelopmentModelProvider
    ):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Security orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            raise AssertionError(
                "QA validation should not run."
            )

        def validate_security(
            self,
            prompt: str,
        ) -> SecurityResult:
            return SecurityResult(
                summary="Security validation blocked.",
                passed=True,
                blockers=[
                    "Security environment unavailable.",
                ],
            )

    run_next_agent(
        project_root=tmp_path,
        provider=BlockingSecurityProvider(),
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["security"]["status"]
        == "BLOCKED"
    )


def test_run_next_agent_marks_security_review_required_when_validation_passes(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {"name": "Test Project"},
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "READY"},
                "devops": {"status": "NOT_STARTED"},
                "sre": {"status": "NOT_STARTED"},
            },
            "security_gate": {
                "status": "NOT_STARTED",
                "reasons": [],
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
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "security": [],
                }
            },
        },
    )

    class PassingSecurityProvider(
        DevelopmentModelProvider
    ):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="Security orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            raise AssertionError(
                "QA validation should not run."
            )

        def validate_security(
            self,
            prompt: str,
        ) -> SecurityResult:
            return SecurityResult(
                summary="Security validation passed.",
                passed=True,
            )

    run_next_agent(
        project_root=tmp_path,
        provider=PassingSecurityProvider(),
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["security"]["status"]
        == "REVIEW_REQUIRED"
    )

    security_gate = updated_state[
        "security_gate"
    ]

    assert (
        security_gate["status"]
        == "READY_FOR_REVIEW"
    )

    assert security_gate["reasons"] == []

    assert (
        security_gate["human_approval"]
        is False
    )


def test_run_next_agent_requires_devops_capable_provider(
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
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "APPROVED"},
                "devops": {"status": "READY"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "devops": [],
                }
            },
        },
    )

    class RunOnlyProvider(ModelProvider):
        def run(
            self,
            context,
        ) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="DevOps orchestration completed.",
            )

    provider = RunOnlyProvider()

    with pytest.raises(
        ValueError,
        match="DevOps-capable provider",
    ):
        run_next_agent(
            project_root=tmp_path,
            provider=provider,
        )


def test_run_next_agent_persists_devops_execution(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    test_file = (
        tmp_path
        / "tests"
        / "test_devops_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_devops_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "APPROVED"},
                "devops": {"status": "READY"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "devops": [],
                }
            },
        },
    )

    class DevOpsExecutionProvider(
        DevelopmentModelProvider
    ):
        def run(
            self,
            context,
        ) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="DevOps orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            raise AssertionError(
                "QA validation should not run."
            )

        def validate_security(
            self,
            prompt: str,
        ) -> SecurityResult:
            raise AssertionError(
                "Security validation should not run."
            )

        def validate_devops(
            self,
            prompt: str,
        ) -> DevOpsResult:
            return DevOpsResult(
                summary="DevOps automation completed.",
                passed=True,
                changes=[
                    DevOpsChange(
                        path=".github/workflows/ci.yml",
                        description="Add CI pipeline.",
                        category="ci_cd",
                    )
                ],
                test_commands=[
                    "python -m pytest "
                    "tests/test_devops_sample.py -q",
                ],
                deployment_ready=True,
                rollback_strategy=(
                    "Redeploy previous stable release."
                ),
            )

    provider = DevOpsExecutionProvider()

    agent_name, _ = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "devops"

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    devops_last_result = updated_state[
        "agents"
    ]["devops"]["last_result"]

    assert devops_last_result[
        "devops_summary"
    ] == "DevOps automation completed."

    assert devops_last_result[
        "devops_model_passed"
    ] is True

    assert devops_last_result[
        "devops_passed"
    ] is True

    assert devops_last_result[
        "devops_changes"
    ] == [
        {
            "path": ".github/workflows/ci.yml",
            "description": "Add CI pipeline.",
            "category": "ci_cd",
        }
    ]

    assert devops_last_result[
        "devops_blockers"
    ] == []

    assert len(
        devops_last_result[
            "devops_test_results"
        ]
    ) == 1

    assert devops_last_result[
        "devops_test_results"
    ][0]["passed"] is True

    assert (
        devops_last_result["deployment_ready"]
        is True
    )

    assert devops_last_result[
        "rollback_strategy"
    ] == "Redeploy previous stable release."

    assert (
        updated_state["agents"]["devops"]["status"]
        == "REVIEW_REQUIRED"
    )


def test_run_next_agent_marks_devops_blocked_when_blockers_exist(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {"name": "Test Project"},
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "APPROVED"},
                "devops": {"status": "READY"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "devops": [],
                }
            },
        },
    )

    class BlockingDevOpsProvider(
        DevelopmentModelProvider
    ):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="DevOps orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            raise AssertionError(
                "QA validation should not run."
            )

        def validate_security(
            self,
            prompt: str,
        ) -> SecurityResult:
            raise AssertionError(
                "Security validation should not run."
            )

        def validate_devops(
            self,
            prompt: str,
        ) -> DevOpsResult:
            return DevOpsResult(
                summary="DevOps validation blocked.",
                passed=True,
                blockers=[
                    "Deployment credentials unavailable.",
                ],
                deployment_ready=True,
                rollback_strategy="Rollback.",
            )

    run_next_agent(
        project_root=tmp_path,
        provider=BlockingDevOpsProvider(),
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["devops"]["status"]
        == "BLOCKED"
    )


def test_run_next_agent_marks_devops_failed_when_not_deployment_ready(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {"name": "Test Project"},
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "APPROVED"},
                "devops": {"status": "READY"},
                "sre": {"status": "NOT_STARTED"},
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
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
            "context": {
                "agents": {
                    "devops": [],
                }
            },
        },
    )

    class FailingDevOpsProvider(
        DevelopmentModelProvider
    ):
        def run(self, context) -> AgentResult:
            return AgentResult(
                status="COMPLETED",
                summary="DevOps orchestration completed.",
            )

        def implement(
            self,
            prompt: str,
        ) -> ImplementationResult:
            raise AssertionError(
                "Developer implementation should not run."
            )

        def validate_qa(
            self,
            prompt: str,
        ) -> QAResult:
            raise AssertionError(
                "QA validation should not run."
            )

        def validate_security(
            self,
            prompt: str,
        ) -> SecurityResult:
            raise AssertionError(
                "Security validation should not run."
            )

        def validate_devops(
            self,
            prompt: str,
        ) -> DevOpsResult:
            return DevOpsResult(
                summary="Deployment is not ready.",
                passed=True,
                deployment_ready=False,
                rollback_strategy="",
            )

    run_next_agent(
        project_root=tmp_path,
        provider=FailingDevOpsProvider(),
    )

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["agents"]["devops"]["status"]
        == "FAILED"
    )
