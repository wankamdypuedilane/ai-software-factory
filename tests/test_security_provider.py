from ai_factory.providers import (
    SecurityProvider,
)
from ai_factory.security_result import (
    SecurityResult,
)


class FakeSecurityProvider(SecurityProvider):
    def validate_security(
        self,
        prompt: str,
    ) -> SecurityResult:
        return SecurityResult(
            summary="Security validation completed.",
            passed=True,
        )


def test_security_provider_contract() -> None:
    provider: SecurityProvider = (
        FakeSecurityProvider()
    )

    result = provider.validate_security(
        "Validate application security."
    )

    assert isinstance(
        result,
        SecurityResult,
    )

    assert result.summary == (
        "Security validation completed."
    )

    assert result.passed is True
