from abc import ABC, abstractmethod
from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.implementation_provider import (
    ImplementationProvider,
)
from ai_factory.qa_result import QAResult


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


class DevelopmentModelProvider(
    ModelProvider,
    ImplementationProvider,
    QAProvider,
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
