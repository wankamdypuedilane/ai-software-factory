from abc import ABC, abstractmethod
from typing import Any


class ModelProvider(ABC):
    """Interface implemented by AI model providers."""

    @abstractmethod
    def run(
        self,
        context: dict[str, Any],
    ) -> str:
        """Execute an agent using the supplied context."""
        raise NotImplementedError


class MockProvider(ModelProvider):
    """Deterministic provider used for local execution and tests."""

    def run(
        self,
        context: dict[str, Any],
    ) -> str:
        agent_name = context["agent_name"]

        return (
            f"Mock execution completed for agent: "
            f"{agent_name}"
        )
