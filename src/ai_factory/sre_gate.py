from dataclasses import dataclass
from typing import Any


@dataclass
class SREGateEvaluation:
    ready: bool
    reasons: list[str]


def evaluate_sre_gate(
    sre_state: dict[str, Any],
) -> SREGateEvaluation:
    """Evaluate whether SRE is ready for human review."""

    reasons: list[str] = []

    if sre_state.get("status") != "REVIEW_REQUIRED":
        reasons.append(
            "SRE is not ready for review."
        )

    last_result = sre_state.get(
        "last_result"
    )

    if not isinstance(last_result, dict):
        reasons.append(
            "SRE result is missing."
        )

        return SREGateEvaluation(
            ready=False,
            reasons=reasons,
        )

    if last_result.get("sre_blockers"):
        reasons.append(
            "SRE has unresolved blockers."
        )

    if last_result.get("sre_passed") is not True:
        reasons.append(
            "SRE validation did not pass."
        )

    if (
        last_result.get("observability_ready")
        is not True
    ):
        reasons.append(
            "Observability is not ready."
        )

    if (
        last_result.get("incident_readiness")
        is not True
    ):
        reasons.append(
            "Incident readiness is not sufficient."
        )

    test_results = last_result.get(
        "sre_test_results",
        [],
    )

    if (
        isinstance(test_results, list)
        and any(
            isinstance(item, dict)
            and item.get("passed") is False
            for item in test_results
        )
    ):
        reasons.append(
            "SRE tests failed."
        )

    findings = last_result.get(
        "sre_findings",
        [],
    )

    if isinstance(findings, list):
        blocking_severities = {
            "Critical",
            "High",
        }

        if any(
            isinstance(finding, dict)
            and finding.get("severity")
            in blocking_severities
            and finding.get("status") != "RESOLVED"
            for finding in findings
        ):
            reasons.append(
                "SRE has unresolved Critical or High severity findings."
            )

    return SREGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
