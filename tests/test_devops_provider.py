from ai_factory.devops_result import (
    DevOpsResult,
)
from ai_factory.providers import (
    DevOpsProvider,
)


class FakeDevOpsProvider(DevOpsProvider):
    def validate_devops(
        self,
        prompt: str,
    ) -> DevOpsResult:
        return DevOpsResult(
            summary="DevOps validation completed.",
            passed=True,
            deployment_ready=True,
            rollback_strategy=(
                "Redeploy the previous stable release."
            ),
        )


def test_devops_provider_contract() -> None:
    provider: DevOpsProvider = (
        FakeDevOpsProvider()
    )

    result = provider.validate_devops(
        "Validate DevOps automation."
    )

    assert isinstance(
        result,
        DevOpsResult,
    )

    assert result.summary == (
        "DevOps validation completed."
    )

    assert result.passed is True
    assert result.deployment_ready is True
