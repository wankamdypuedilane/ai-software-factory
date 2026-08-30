from ai_factory.security_result import (
    SecurityFinding,
    SecurityResult,
)


def test_security_result_stores_findings_and_test_commands() -> None:
    finding = SecurityFinding(
        id="SEC-001",
        title="Hard-coded secret detected",
        severity="High",
        affected_component="backend",
        description="A secret is committed in source code.",
        impact="Credential exposure.",
        evidence="src/config.py",
        recommended_remediation=(
            "Move the secret to environment variables."
        ),
        priority="P1",
        status="OPEN",
    )

    result = SecurityResult(
        summary="Security validation completed.",
        passed=False,
        findings=[
            finding,
        ],
        test_commands=[
            "python -m pytest tests/test_security.py -q",
        ],
    )

    assert result.summary == (
        "Security validation completed."
    )

    assert result.passed is False
    assert len(result.findings) == 1

    assert result.findings[0].id == "SEC-001"
    assert result.findings[0].severity == "High"
    assert (
        result.findings[0].affected_component
        == "backend"
    )

    assert result.test_commands == [
        "python -m pytest tests/test_security.py -q",
    ]

    assert result.blockers == []


def test_security_result_defaults_are_independent() -> None:
    first = SecurityResult(
        summary="First security run.",
        passed=True,
    )

    second = SecurityResult(
        summary="Second security run.",
        passed=True,
    )

    first.test_commands.append(
        "pytest"
    )

    first.blockers.append(
        "Security environment unavailable."
    )

    assert first.test_commands == [
        "pytest"
    ]
    assert second.test_commands == []

    assert first.blockers == [
        "Security environment unavailable."
    ]
    assert second.blockers == []
