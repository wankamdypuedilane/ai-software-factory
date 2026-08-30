from typing import Protocol

from ai_factory.implementation_result import (
    ImplementationResult,
)


class ImplementationProvider(Protocol):
    """Provider capable of executing one implementation task."""

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        """Execute one focused implementation prompt."""
        ...
