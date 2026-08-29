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
