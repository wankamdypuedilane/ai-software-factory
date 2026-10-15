"""Bound on DevOps retry cycles.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. Developer, QA and Security are
bounded; DevOps was not. Requiring objective evidence for DevOps success made
that observable rather than latent.

The bound is 2, established from the DevOps lifecycle rather than by analogy:
`DevOpsResult.changes` are recorded in state but never applied to the
workspace by the runtime, which only executes the declared commands. A
repeated DevOps cycle therefore inspects a governed state that DevOps itself
never altered, with an identical prompt.

Only the pure counter arithmetic is shared with the other guards: those
functions take plain values rather than state, so nothing about Developer, QA
or Security behaviour changes.
"""

from typing import Any

from ai_factory.devops_evidence import (
    describe_devops_evidence,
    devops_evidence_satisfied,
)
from ai_factory.replan_guard import (
    next_repeated_failures,
    next_replan_count,
)


MAX_DEVOPS_RETRIES = 2

DEVOPS_RETRY_COUNT_FIELD = "devops_retry_count"
DEVOPS_REPEATED_FAILURES_FIELD = "devops_repeated_failures"
DEVOPS_FAILURE_SIGNATURE_FIELD = "devops_failure_signature"


class NonConvergingDevOpsError(ValueError):
    """DevOps keeps failing without converging."""


def get_devops_result(
    state: dict[str, Any],
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict):
        return {}

    devops = agents.get("devops")

    if not isinstance(devops, dict):
        return {}

    last_result = devops.get("last_result")

    return last_result if isinstance(last_result, dict) else {}


def _counter(
    state: dict[str, Any],
    field: str,
) -> int:
    value = get_devops_result(state).get(field)

    return value if isinstance(value, int) and value > 0 else 0


def get_devops_retry_count(
    state: dict[str, Any],
) -> int:
    """How many DevOps cycles already failed, from persisted state only."""

    return _counter(state, DEVOPS_RETRY_COUNT_FIELD)


def get_devops_repeated_failures(
    state: dict[str, Any],
) -> int:
    return _counter(state, DEVOPS_REPEATED_FAILURES_FIELD)


def get_devops_failure_signature(
    state: dict[str, Any],
) -> str:
    value = get_devops_result(state).get(DEVOPS_FAILURE_SIGNATURE_FIELD)

    return value if isinstance(value, str) else ""


def build_devops_failure_signature(
    devops_last_result: dict[str, Any],
) -> str:
    """Describe how a DevOps cycle failed, from structured evidence only.

    The engine's reason codes and the failing command strings are the stable
    parts. The summary, the change descriptions and the rollback text are
    the agent's wording and are excluded.

    The rollback strategy participates only through its presence or absence.
    Whether a strategy exists is structural; what it says is prose the
    engine cannot interpret, and two different rollback texts describing the
    same failing cycle produce the same signature.
    """

    test_results = devops_last_result.get("devops_test_results")
    test_results = test_results if isinstance(test_results, list) else []

    evidence = describe_devops_evidence(
        test_results=test_results,
        blockers=devops_last_result.get("devops_blockers", []),
        deployment_ready=devops_last_result.get("deployment_ready"),
        rollback_strategy=devops_last_result.get("rollback_strategy"),
    )

    model_passed = (
        devops_last_result.get("devops_model_passed") is True
    )

    if devops_evidence_satisfied(evidence) and model_passed:
        return ""

    parts: list[str] = []

    if evidence.executed_checks < 1:
        parts.append("no_evidence")

    if evidence.failed_checks:
        parts.append("failed_checks")

    if evidence.blocking_blockers:
        parts.append(f"blocking_blockers:{evidence.blocking_blockers}")

    if not evidence.deployment_declared:
        parts.append("deployment_not_ready")

    if not evidence.rollback_declared:
        parts.append("rollback_missing")

    if not model_passed:
        parts.append("model_reported_failure")

    parts.extend(
        sorted(
            {
                item.get("command")
                for item in test_results
                if (
                    isinstance(item, dict)
                    and item.get("passed") is False
                    and isinstance(item.get("command"), str)
                )
            }
        )
    )

    return "|".join(parts)


def advance_devops_retry_state(
    devops_last_result: dict[str, Any],
    previous_count: int,
    previous_signature: str,
    previous_repeated: int,
    cycle_failed: bool,
) -> None:
    """Record what this cycle costs the budget.

    The only place two consecutive cycles are both known, so repetition is
    computed here and merely read by the guard.
    """

    signature = (
        build_devops_failure_signature(devops_last_result)
        if cycle_failed
        else ""
    )

    devops_last_result[DEVOPS_RETRY_COUNT_FIELD] = next_replan_count(
        previous_count,
        failed=cycle_failed,
    )

    devops_last_result[DEVOPS_FAILURE_SIGNATURE_FIELD] = signature

    devops_last_result[
        DEVOPS_REPEATED_FAILURES_FIELD
    ] = next_repeated_failures(
        previous_repeated,
        previous_signature,
        signature,
    )


def is_devops_budget_exhausted(
    state: dict[str, Any],
) -> bool:
    """Whether the autonomous DevOps search has legitimately run out."""

    return (
        get_devops_retry_count(state) >= MAX_DEVOPS_RETRIES
        or get_devops_repeated_failures(state) >= 1
    )


def assert_devops_retry_budget(
    state: dict[str, Any],
) -> None:
    """Refuse a DevOps cycle that cannot be expected to converge.

    Reads persisted counters only, so restarting the CLI cannot quietly
    reopen the loop. Called before any provider call, so an exhausted budget
    costs nothing.
    """

    if get_devops_repeated_failures(state) >= 1:
        raise NonConvergingDevOpsError(
            "NON_CONVERGING_DEVOPS: two consecutive DevOps cycles produced "
            "the same failure. The workflow stopped instead of spending "
            "another provider call. Inspect the persisted DevOps evidence, "
            "deployment readiness and rollback strategy of the last attempt."
        )

    count = get_devops_retry_count(state)

    if count >= MAX_DEVOPS_RETRIES:
        raise NonConvergingDevOpsError(
            "NON_CONVERGING_DEVOPS: DevOps validation is not converging: "
            f"{count} DevOps cycles failed (limit {MAX_DEVOPS_RETRIES}). "
            "The workflow stopped instead of spending another provider "
            "call. DevOps does not apply its changes to the workspace, so "
            "a further attempt would inspect the same state again."
        )
