from abc import ABC, abstractmethod
from typing import Any

from ai_factory.agent_result import (
    AgentArtifactRequest,
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.devops_result import (
    DevOpsResult,
)
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)
from ai_factory.implementation_provider import (
    ImplementationProvider,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.qa_result import QAResult
from ai_factory.sre_result import (
    SREResult,
)
from ai_factory.security_result import (
    SecurityResult,
)


class ModelProvider(ABC):
    """Interface implemented by AI model providers."""

    @abstractmethod
    def run(
        self,
        context: dict[str, Any],
    ) -> AgentResult:
        """Execute an agent using the supplied context."""
        raise NotImplementedError


class QAProvider:
    """Provider capable of performing structured QA validation."""

    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        raise NotImplementedError


class SecurityProvider:
    """Provider capable of performing structured security validation."""

    def validate_security(
        self,
        prompt: str,
    ) -> SecurityResult:
        raise NotImplementedError


class DevOpsProvider:
    """Provider capable of performing structured DevOps validation."""

    def validate_devops(
        self,
        prompt: str,
    ) -> DevOpsResult:
        raise NotImplementedError


class SREProvider:
    """Provider capable of performing structured SRE validation."""

    def validate_sre(
        self,
        prompt: str,
    ) -> SREResult:
        raise NotImplementedError


class DevelopmentModelProvider(
    ModelProvider,
    ImplementationProvider,
    QAProvider,
    SecurityProvider,
    DevOpsProvider,
    SREProvider,
):
    """Provider capable of agent and implementation execution."""

    pass


class MockProvider(
    DevelopmentModelProvider,
):
    """Deterministic provider used for local execution and tests.

    With `ask_questions`, the Product agent first asks one structured
    question and completes once the human input holds an answer, so the
    question flow of an interface can be exercised without a model.
    """

    def __init__(
        self,
        ask_questions: bool = False,
    ) -> None:
        self.ask_questions = ask_questions

    def run(
        self,
        context: dict[str, Any],
    ) -> AgentResult:
        agent_name = context["agent_name"]

        summary = (
            f"Mock execution completed for agent: "
            f"{agent_name}"
        )

        if (
            agent_name == "product"
            and getattr(self, "ask_questions", False)
            and "## Answers" not in (context.get("human_input") or "")
        ):
            question = "Who should be able to use the product?"

            return AgentResult(
                status="NEEDS_INPUT",
                summary="The audience decides whether accounts are needed.",
                questions=[question],
                question_details=[
                    {
                        "question": question,
                        "why": "It decides whether user accounts are needed.",
                        "needs_owner_text": False,
                        "options": [
                            {
                                "label": "Anyone, without an account",
                                "detail": "Simplest for users.",
                                "recommended": True,
                            },
                            {
                                "label": "Registered users only",
                                "detail": "Adds sign-up and login.",
                                "recommended": False,
                            },
                        ],
                    }
                ],
            )

        if agent_name == "product":
            return AgentResult(
                status="COMPLETED",
                summary=summary,
            )

        if agent_name == "ux_ui":
            return AgentResult(
                status="COMPLETED",
                summary=summary,
                artifact_requests=[
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "accessibility-requirements.md"
                        ),
                        purpose=(
                            "Define accessibility requirements."
                        ),
                    ),
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "design-system.md"
                        ),
                        purpose=(
                            "Define the project design system."
                        ),
                    ),
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "information-architecture.md"
                        ),
                        purpose=(
                            "Define information architecture."
                        ),
                    ),
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "responsive-rules.md"
                        ),
                        purpose=(
                            "Define responsive design rules."
                        ),
                    ),
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "screen-specs.md"
                        ),
                        purpose=(
                            "Define screen specifications."
                        ),
                    ),
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "user-flows.md"
                        ),
                        purpose=(
                            "Define primary user flows."
                        ),
                    ),
                    AgentArtifactRequest(
                        path=(
                            "design/ux-ui/"
                            "wireframes.md"
                        ),
                        purpose=(
                            "Define textual wireframes."
                        ),
                    ),
                ],
            )

        if agent_name == "architect":
            return AgentResult(
                status="COMPLETED",
                summary=summary,
                metadata={
                    "technology_proposal": {
                        "components": [
                            {
                                "name": "backend",
                                "technology": "Python",
                                "rationale": (
                                    "Deterministic backend "
                                    "technology for mock execution."
                                ),
                            },
                            {
                                "name": "database",
                                "technology": "SQLite",
                                "rationale": (
                                    "Simple local persistence "
                                    "for mock execution."
                                ),
                            },
                        ],
                    },
                },
            )

        if agent_name == "developer":
            return AgentResult(
                status="COMPLETED",
                summary=summary,
                implementation_requests=[
                    AgentImplementationRequest(
                        id="MOCK-001",
                        title="Create mock application",
                        purpose=(
                            "Create a minimal deterministic "
                            "application for local Factory execution."
                        ),
                        kind=ImplementationTaskKind.IMPLEMENTATION,
                        scope=ImplementationScope.TASK,
                        verification=VerificationPolicy(
                            allow_full_suite=False,
                            baseline_required=True,
                        ),
                    ),
                ],
            )

        if agent_name in {
            "qa",
            "security",
            "devops",
            "sre",
        }:
            return AgentResult(
                status="COMPLETED",
                summary=summary,
            )

        raise ValueError(
            f"Unsupported mock agent: {agent_name}"
        )

    def generate(
        self,
        prompt: str,
    ) -> str:
        """Generate deterministic artifact content."""

        return (
            "# Mock Generated Artifact\n\n"
            "This artifact was generated by the "
            "AI Software Factory MockProvider.\n"
        )

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        """Return a deterministic implementation result."""

        return ImplementationResult(
            task_id="MOCK-001",
            summary=(
                "Mock implementation completed."
            ),
            files=[
                ImplementationFileChange(
                    path="src/mock_app.py",
                    content=(
                        '"""Mock application generated by '
                        'AI Software Factory."""\n\n'
                        "def healthcheck() -> str:\n"
                        '    return "ok"\n'
                    ),
                ),
                # The mock models a well-formed agent, and a unit that
                # writes governed files must say what verifies them.
                ImplementationFileChange(
                    path="tests/test_mock_app.py",
                    content=(
                        "import sys\n"
                        "\n"
                        'sys.path.insert(0, "src")\n'
                        "\n"
                        "from mock_app import healthcheck\n"
                        "\n"
                        "\n"
                        "def test_healthcheck() -> None:\n"
                        '    assert healthcheck() == "ok"\n'
                    ),
                ),
            ],
            tests=[
                "python -m pytest tests/test_mock_app.py -q",
            ],
            blockers=[],
        )

    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        """Return a successful deterministic QA result."""

        return QAResult(
            summary="Mock QA validation passed.",
            passed=True,
            defects=[],
            # The mock models a well-formed QA agent: it declares the
            # validation the engine executes, because a claim the engine
            # cannot execute never passes QA.
            test_commands=[
                "python -m pytest tests/test_mock_app.py -q",
            ],
            blockers=[],
        )

    def validate_security(
        self,
        prompt: str,
    ) -> SecurityResult:
        """Return a successful deterministic security result."""

        return SecurityResult(
            summary=(
                "Mock security validation passed."
            ),
            passed=True,
            findings=[],
            # The mock models a well-formed security agent: it declares the
            # validation the engine executes, because a claim the engine
            # cannot execute never clears the security phase.
            test_commands=[
                "python -m pytest tests/test_mock_app.py -q",
            ],
            blockers=[],
        )

    def validate_devops(
        self,
        prompt: str,
    ) -> DevOpsResult:
        """Return a successful deterministic DevOps result."""

        return DevOpsResult(
            summary=(
                "Mock DevOps validation passed."
            ),
            passed=True,
            changes=[],
            # The mock models a well-formed DevOps agent: it declares the
            # validation the engine executes, because a deployment claim
            # the engine cannot check never opens the gate.
            test_commands=[
                "python -m pytest tests/test_mock_app.py -q",
            ],
            blockers=[],
            deployment_ready=True,
            rollback_strategy=(
                "Restore the previous mock release."
            ),
        )

    def validate_sre(
        self,
        prompt: str,
    ) -> SREResult:
        """Return a successful deterministic SRE result."""

        return SREResult(
            summary="Mock SRE validation passed.",
            passed=True,
            findings=[],
            # The mock models a well-formed SRE agent: it declares the
            # validation the engine executes, because a production-readiness
            # claim the engine cannot check never opens the gate.
            test_commands=[
                "python -m pytest tests/test_mock_app.py -q",
            ],
            blockers=[],
            observability_ready=True,
            incident_readiness=True,
        )