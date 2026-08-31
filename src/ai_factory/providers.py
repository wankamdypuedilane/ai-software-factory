from abc import ABC, abstractmethod
from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.devops_result import (
    DevOpsResult,
)
from ai_factory.implementation_provider import (
    ImplementationProvider,
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


class MockProvider(ModelProvider):
    """Deterministic provider used for local execution and tests."""

    def run(
        self,
        context: dict[str, Any],
    ) -> AgentResult:
        agent_name = context["agent_name"]

        return AgentResult(
            status="COMPLETED",
            summary=(
                f"Mock execution completed for agent: "
                f"{agent_name}"
            ),
        )
