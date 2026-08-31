from ai_factory.providers import (
    SREProvider,
)
from ai_factory.sre_result import (
    SREResult,
)


class FakeSREProvider(SREProvider):
    def validate_sre(
        self,
        prompt: str,
    ) -> SREResult:
        return SREResult(
            summary="SRE validation completed.",
            passed=True,
            observability_ready=True,
            incident_readiness=True,
        )


def test_sre_provider_contract() -> None:
    provider: SREProvider = (
        FakeSREProvider()
    )

    result = provider.validate_sre(
        "Validate reliability and observability."
    )

    assert isinstance(
        result,
        SREResult,
    )

    assert result.summary == (
        "SRE validation completed."
    )

    assert result.passed is True
    assert result.observability_ready is True
    assert result.incident_readiness is True
