"""Bound on Security retry cycles.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. Security had no bound, so an
agent that kept failing was selected again, called the provider again, and
failed again without limit. Requiring executed evidence for Security success
turned that from a latent defect into an observable hang.

The bound is 2, for the same structural reason as QA and not by analogy:
`SecurityResult` carries no file changes, so a Security cycle reviews a
workspace Security itself never modified. Repeating it reads identical
artifacts with an identical prompt, and the second attempt is already at the
useful limit.

Only the pure counter arithmetic is shared with the other guards: those
functions take plain values rather than state, so nothing about Developer or
QA behaviour changes.
"""

from typing import Any

from ai_factory.replan_guard import (
    next_repeated_failures,
    next_replan_count,
)
from ai_factory.security_evidence import (
    describe_security_evidence,
    security_evidence_satisfied,
)


MAX_SECURITY_RETRIES = 2

SECURITY_RETRY_COUNT_FIELD = "security_retry_count"
SECURITY_REPEATED_FAILURES_FIELD = "security_repeated_failures"
SECURITY_FAILURE_SIGNATURE_FIELD = "security_failure_signature"


class NonConvergingSecurityError(ValueError):
    """Security keeps failing without converging."""


def get_security_result(
    state: dict[str, Any],
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict):
        return {}

    security = agents.get("security")

    if not isinstance(security, dict):
        return {}

    last_result = security.get("last_result")

    return last_result if isinstance(last_result, dict) else {}


def _counter(
    state: dict[str, Any],
    field: str,
) -> int:
    value = get_security_result(state).get(field)

    return value if isinstance(value, int) and value > 0 else 0


def get_security_retry_count(
    state: dict[str, Any],
) -> int:
    """How many Security cycles already failed, from persisted state only."""

    return _counter(state, SECURITY_RETRY_COUNT_FIELD)


def get_security_repeated_failures(
    state: dict[str, Any],
) -> int:
    return _counter(state, SECURITY_REPEATED_FAILURES_FIELD)


def get_security_failure_signature(
    state: dict[str, Any],
) -> str:
    value = get_security_result(state).get(
        SECURITY_FAILURE_SIGNATURE_FIELD
    )

    return value if isinstance(value, str) else ""


def build_security_failure_signature(
    security_last_result: dict[str, Any],
) -> str:
    """Describe how a Security cycle failed, from structured evidence only.

    The engine's own reason codes and the failing command strings are the
    stable parts. Finding identifiers, titles, descriptions, impact,
    remediation text and the summary are the agent's wording and are all
    excluded.

    The unresolved-findings count does participate, but only as the existing
    Security policy already treats it: the declared severity and status are
    the agent's assertions, and counting them here claims nothing more than
    the gate already claims about them.
    """

    test_results = security_last_result.get("security_test_results")
    test_results = test_results if isinstance(test_results, list) else []

    findings = security_last_result.get("security_findings")
    findings = findings if isinstance(findings, list) else []

    evidence = describe_security_evidence(
        test_results=test_results,
        blockers=security_last_result.get("security_blockers", []),
        findings=findings,
    )

    model_passed = (
        security_last_result.get("security_model_passed") is True
    )

    if security_evidence_satisfied(evidence) and model_passed:
        return ""

    parts: list[str] = []

    if evidence.executed_checks < 1:
        parts.append("no_evidence")

    if evidence.failed_checks:
        parts.append("failed_checks")

    if evidence.blocking_blockers:
        parts.append(f"blocking_blockers:{evidence.blocking_blockers}")

    if evidence.unresolved_findings:
        parts.append(
            f"unresolved_findings:{evidence.unresolved_findings}"
        )

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


def advance_security_retry_state(
    security_last_result: dict[str, Any],
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
        build_security_failure_signature(security_last_result)
        if cycle_failed
        else ""
    )

    security_last_result[SECURITY_RETRY_COUNT_FIELD] = next_replan_count(
        previous_count,
        failed=cycle_failed,
    )

    security_last_result[SECURITY_FAILURE_SIGNATURE_FIELD] = signature

    security_last_result[
        SECURITY_REPEATED_FAILURES_FIELD
    ] = next_repeated_failures(
        previous_repeated,
        previous_signature,
        signature,
    )


def is_security_budget_exhausted(
    state: dict[str, Any],
) -> bool:
    """Whether the autonomous Security search has legitimately run out."""

    return (
        get_security_retry_count(state) >= MAX_SECURITY_RETRIES
        or get_security_repeated_failures(state) >= 1
    )


def assert_security_retry_budget(
    state: dict[str, Any],
) -> None:
    """Refuse a Security cycle that cannot be expected to converge.

    Reads persisted counters only, so restarting the CLI cannot quietly
    reopen the loop. Called before any provider call, so an exhausted budget
    costs nothing.
    """

    if get_security_repeated_failures(state) >= 1:
        raise NonConvergingSecurityError(
            "NON_CONVERGING_SECURITY: two consecutive Security cycles "
            "produced the same failure. The workflow stopped instead of "
            "spending another provider call. Inspect the persisted "
            "security evidence, findings and blockers of the last attempt."
        )

    count = get_security_retry_count(state)

    if count >= MAX_SECURITY_RETRIES:
        raise NonConvergingSecurityError(
            "NON_CONVERGING_SECURITY: security validation is not "
            f"converging: {count} Security cycles failed "
            f"(limit {MAX_SECURITY_RETRIES}). The workflow stopped instead "
            "of spending another provider call. Security does not modify "
            "the workspace, so a further attempt would review the same "
            "artifacts again."
        )
