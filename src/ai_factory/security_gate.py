from dataclasses import dataclass
from typing import Any


@dataclass
class SecurityGateEvaluation:
    ready: bool
    reasons: list[str]


def evaluate_security_gate(
    security_state: dict[str, Any],
) -> SecurityGateEvaluation:
    """Evaluate whether Security is ready for human review."""

    reasons: list[str] = []

    if security_state.get("status") != "REVIEW_REQUIRED":
        reasons.append(
            "Security is not ready for review."
        )

    last_result = security_state.get(
        "last_result"
    )

    if not isinstance(last_result, dict):
        reasons.append(
            "Security result is missing."
        )

        return SecurityGateEvaluation(
            ready=False,
            reasons=reasons,
        )

    if last_result.get("security_blockers"):
        reasons.append(
            "Security has unresolved blockers."
        )

    if last_result.get("security_passed") is not True:
        reasons.append(
            "Security validation did not pass."
        )

    test_results = last_result.get(
        "security_test_results",
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
            "Security tests failed."
        )

    findings = last_result.get(
        "security_findings",
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
                "Security has unresolved Critical or High severity findings."
            )

    return SecurityGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
