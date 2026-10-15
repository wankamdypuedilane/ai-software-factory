from ai_factory.devops_evidence import (
    describe_devops_evidence,
    devops_evidence_reasons,
    devops_evidence_satisfied,
)
from dataclasses import dataclass
from typing import Any


@dataclass
class DevOpsGateEvaluation:
    ready: bool
    reasons: list[str]


def evaluate_devops_gate(
    devops_state: dict[str, Any],
) -> DevOpsGateEvaluation:
    """Evaluate whether DevOps is ready for human review."""

    reasons: list[str] = []

    if devops_state.get("status") != "REVIEW_REQUIRED":
        reasons.append(
            "DevOps is not ready for review."
        )

    last_result = devops_state.get(
        "last_result"
    )

    if not isinstance(last_result, dict):
        reasons.append(
            "DevOps result is missing."
        )

        return DevOpsGateEvaluation(
            ready=False,
            reasons=reasons,
        )

    test_results = last_result.get(
        "devops_test_results",
        [],
    )

    # Re-derived from persisted evidence rather than trusted from the stored
    # `devops_passed` flag. Every requirement the gate already enforced is
    # still enforced, with the same wording; what is added is that a
    # deployment claim must rest on something the engine executed.
    evidence = describe_devops_evidence(
        test_results=test_results if isinstance(test_results, list) else [],
        blockers=last_result.get("devops_blockers", []),
        deployment_ready=last_result.get("deployment_ready"),
        rollback_strategy=last_result.get("rollback_strategy"),
    )

    reasons.extend(
        devops_evidence_reasons(evidence)
    )

    # The agent keeps its veto: it may report a problem over green evidence,
    # and the gate honours that. It may not open the gate on its own.
    if (
        devops_evidence_satisfied(evidence)
        and last_result.get("devops_passed") is not True
    ):
        reasons.append(
            "DevOps validation did not pass."
        )

    return DevOpsGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
