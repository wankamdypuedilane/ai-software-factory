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
    """Deterministic provider used for local execution and tests."""

    def run(
        self,
        context: dict[str, Any],
    ) -> AgentResult:
        agent_name = context["agent_name"]

        summary = (
            f"Mock execution completed for agent: "
            f"{agent_name}"
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
            ],
            tests=[],
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
            test_commands=[],
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
            test_commands=[],
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
            test_commands=[],
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
            test_commands=[],
            blockers=[],
            observability_ready=True,
            incident_readiness=True,
        )