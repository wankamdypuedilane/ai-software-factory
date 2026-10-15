from ai_factory.security_evidence import (
    describe_security_evidence,
    security_evidence_reasons,
    security_evidence_satisfied,
)
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

    test_results = last_result.get(
        "security_test_results",
        [],
    )

    findings = last_result.get(
        "security_findings",
        [],
    )

    # Re-derived from persisted evidence rather than trusted from the stored
    # `security_passed` flag. The runtime already decides the same way, so a
    # state this engine wrote is unaffected - and a state written by an
    # older engine, restored, or edited by hand can no longer assert a
    # success that no executed check supports.
    evidence = describe_security_evidence(
        test_results=test_results if isinstance(test_results, list) else [],
        blockers=last_result.get("security_blockers", []),
        findings=findings if isinstance(findings, list) else [],
    )

    reasons.extend(
        security_evidence_reasons(evidence)
    )

    # The agent keeps its veto: it may report a problem over green checks,
    # and the gate honours that. It may not open the gate on its own.
    if (
        security_evidence_satisfied(evidence)
        and last_result.get("security_passed") is not True
    ):
        reasons.append(
            "Security validation did not pass."
        )

    return SecurityGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
