from ai_factory.implementation_provider import (
    ImplementationProvider,
)
from ai_factory.implementation_result import (
    ImplementationResult,
)


class FakeImplementationProvider:
    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        return ImplementationResult(
            task_id="US-001",
            summary="Implementation completed.",
        )


def test_implementation_provider_contract() -> None:
    provider: ImplementationProvider = (
        FakeImplementationProvider()
    )

    result = provider.implement(
        "Implement US-001"
    )

    assert isinstance(
        result,
        ImplementationResult,
    )
    assert result.task_id == "US-001"
    assert result.summary == "Implementation completed."
