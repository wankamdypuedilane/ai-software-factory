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

    if last_result.get("devops_blockers"):
        reasons.append(
            "DevOps has unresolved blockers."
        )

    if last_result.get("devops_passed") is not True:
        reasons.append(
            "DevOps validation did not pass."
        )

    if last_result.get("deployment_ready") is not True:
        reasons.append(
            "Deployment is not ready."
        )

    test_results = last_result.get(
        "devops_test_results",
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
            "DevOps tests failed."
        )

    rollback_strategy = last_result.get(
        "rollback_strategy"
    )

    if (
        not isinstance(rollback_strategy, str)
        or not rollback_strategy.strip()
    ):
        reasons.append(
            "Rollback strategy is missing."
        )

    return DevOpsGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
