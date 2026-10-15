from ai_factory.sre_evidence import (
    describe_sre_evidence,
    sre_evidence_reasons,
    sre_evidence_satisfied,
)
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

    test_results = last_result.get(
        "sre_test_results",
        [],
    )

    findings = last_result.get(
        "sre_findings",
        [],
    )

    # Re-derived from persisted evidence rather than trusted from the stored
    # `sre_passed` flag. Every requirement the gate already enforced is
    # still enforced, with the same wording; what is added is that a
    # production-readiness claim must rest on something the engine executed.
    evidence = describe_sre_evidence(
        test_results=test_results if isinstance(test_results, list) else [],
        blockers=last_result.get("sre_blockers", []),
        findings=findings if isinstance(findings, list) else [],
        observability_ready=last_result.get("observability_ready"),
        incident_readiness=last_result.get("incident_readiness"),
    )

    reasons.extend(
        sre_evidence_reasons(evidence)
    )

    # The agent keeps its veto: it may report a problem over green evidence,
    # and the gate honours that. It may not open the gate on its own.
    if (
        sre_evidence_satisfied(evidence)
        and last_result.get("sre_passed") is not True
    ):
        reasons.append(
            "SRE validation did not pass."
        )

    return SREGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
