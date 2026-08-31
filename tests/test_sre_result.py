from ai_factory.sre_result import (
    SREFinding,
    SREResult,
)


def test_sre_result_stores_reliability_state() -> None:
    finding = SREFinding(
        id="SRE-001",
        title="Missing application health check",
        severity="High",
        category="health_check",
        description=(
            "The application exposes no health endpoint."
        ),
        recommendation=(
            "Add a health endpoint for deployment monitoring."
        ),
    )

    result = SREResult(
        summary="SRE validation completed.",
        passed=True,
        findings=[
            finding,
        ],
        test_commands=[
            "python -m pytest -q",
        ],
        observability_ready=True,
        incident_readiness=True,
    )

    assert result.summary == (
        "SRE validation completed."
    )

    assert result.passed is True
    assert len(result.findings) == 1

    assert result.findings[0].id == "SRE-001"
    assert result.findings[0].severity == "High"
    assert result.findings[0].category == "health_check"
    assert result.findings[0].status == "OPEN"

    assert result.test_commands == [
        "python -m pytest -q",
    ]

    assert result.blockers == []
    assert result.observability_ready is True
    assert result.incident_readiness is True


def test_sre_result_defaults_are_independent() -> None:
    first = SREResult(
        summary="First SRE run.",
        passed=True,
    )

    second = SREResult(
        summary="Second SRE run.",
        passed=True,
    )

    first.findings.append(
        SREFinding(
            id="SRE-001",
            title="Missing metrics",
            severity="Medium",
            category="metrics",
            description="Metrics are unavailable.",
            recommendation="Expose service metrics.",
        )
    )

    first.blockers.append(
        "Observability environment unavailable."
    )

    assert len(first.findings) == 1
    assert second.findings == []

    assert first.blockers == [
        "Observability environment unavailable."
    ]
    assert second.blockers == []

    assert first.observability_ready is False
    assert second.observability_ready is False

    assert first.incident_readiness is False
    assert second.incident_readiness is False
