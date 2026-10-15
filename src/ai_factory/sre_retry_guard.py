"""Bound on SRE retry cycles.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. Developer, QA, Security and
DevOps are bounded; SRE was not. Requiring objective evidence for SRE
success made that observable rather than latent: `sre == FAILED` selected
SRE again, called the provider again, and failed again without limit. SRE
was the last downstream validation agent able to consume provider calls
without a bound.

The bound is 2, established from the SRE lifecycle rather than by analogy.
`SREResult` declares `summary`, `passed`, `findings`, `test_commands`,
`blockers`, `observability_ready` and `incident_readiness` - and nothing
else. It carries no file changes at all, not even the unapplied `changes[]`
that DevOps declares, and `run_sre_validation` only executes the commands
the agent names. A repeated SRE cycle therefore evaluates the identical
governed product and operational state with an identical prompt: the second
attempt is already at the useful limit, and it exists only so that a
genuinely transient operational check - a smoke test against a service that
was still starting - gets one honest second chance. A third has nothing new
to work with. A limit of 1 would forbid that legitimate retry; a limit
above 2 would only repeat an identical evaluation at provider cost.

Only the pure counter arithmetic is shared with the other guards: those
functions take plain values rather than state, so nothing about Developer,
QA, Security or DevOps behaviour changes.
"""

from typing import Any

from ai_factory.replan_guard import (
    next_repeated_failures,
    next_replan_count,
)
from ai_factory.sre_evidence import (
    describe_sre_evidence,
    sre_evidence_satisfied,
)


MAX_SRE_RETRIES = 2

SRE_RETRY_COUNT_FIELD = "sre_retry_count"
SRE_REPEATED_FAILURES_FIELD = "sre_repeated_failures"
SRE_FAILURE_SIGNATURE_FIELD = "sre_failure_signature"


class NonConvergingSREError(ValueError):
    """SRE keeps failing without converging."""


def get_sre_result(
    state: dict[str, Any],
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict):
        return {}

    sre = agents.get("sre")

    if not isinstance(sre, dict):
        return {}

    last_result = sre.get("last_result")

    return last_result if isinstance(last_result, dict) else {}


def _counter(
    state: dict[str, Any],
    field: str,
) -> int:
    value = get_sre_result(state).get(field)

    return value if isinstance(value, int) and value > 0 else 0


def get_sre_retry_count(
    state: dict[str, Any],
) -> int:
    """How many SRE cycles already failed, from persisted state only."""

    return _counter(state, SRE_RETRY_COUNT_FIELD)


def get_sre_repeated_failures(
    state: dict[str, Any],
) -> int:
    return _counter(state, SRE_REPEATED_FAILURES_FIELD)


def get_sre_failure_signature(
    state: dict[str, Any],
) -> str:
    value = get_sre_result(state).get(SRE_FAILURE_SIGNATURE_FIELD)

    return value if isinstance(value, str) else ""


def build_sre_failure_signature(
    sre_last_result: dict[str, Any],
) -> str:
    """Describe how an SRE cycle failed, from structured evidence only.

    The engine's own reason codes and the failing command strings are the
    stable parts. The summary, and every finding's identifier, title,
    category, description and recommendation, are the agent's wording and
    are all excluded - identifiers included, because the agent renumbers
    findings between cycles exactly as the Developer renames tasks.

    Both readiness flags participate as declared booleans, never as prose.
    They are assertions the agent makes about itself, and recording whether
    they were declared claims nothing the execution rule and the gate do not
    already claim about them.

    The counts of blocking findings and blocking blockers participate too,
    but only through the SRE policy already declared in `sre_evidence`:
    `BLOCKING_FINDING_SEVERITIES` and an exact `RESOLVED` status. Severity
    and status stay model assertions; counting them here asserts nothing
    further about their truth.
    """

    test_results = sre_last_result.get("sre_test_results")
    test_results = test_results if isinstance(test_results, list) else []

    findings = sre_last_result.get("sre_findings")
    findings = findings if isinstance(findings, list) else []

    evidence = describe_sre_evidence(
        test_results=test_results,
        blockers=sre_last_result.get("sre_blockers", []),
        findings=findings,
        observability_ready=sre_last_result.get("observability_ready"),
        incident_readiness=sre_last_result.get("incident_readiness"),
    )

    model_passed = sre_last_result.get("sre_model_passed") is True

    if sre_evidence_satisfied(evidence) and model_passed:
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

    if not evidence.observability_declared:
        parts.append("observability_not_ready")

    if not evidence.incident_readiness_declared:
        parts.append("incident_readiness_not_ready")

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


def advance_sre_retry_state(
    sre_last_result: dict[str, Any],
    previous_count: int,
    previous_signature: str,
    previous_repeated: int,
    cycle_failed: bool,
) -> None:
    """Record what this cycle costs the budget.

    The only place two consecutive cycles are both known, so repetition is
    computed here and merely read by the guard. A successful cycle writes an
    empty signature and a zero count, so a later independent SRE phase never
    inherits stale non-convergence state.
    """

    signature = (
        build_sre_failure_signature(sre_last_result)
        if cycle_failed
        else ""
    )

    sre_last_result[SRE_RETRY_COUNT_FIELD] = next_replan_count(
        previous_count,
        failed=cycle_failed,
    )

    sre_last_result[SRE_FAILURE_SIGNATURE_FIELD] = signature

    sre_last_result[SRE_REPEATED_FAILURES_FIELD] = next_repeated_failures(
        previous_repeated,
        previous_signature,
        signature,
    )


def is_sre_budget_exhausted(
    state: dict[str, Any],
) -> bool:
    """Whether the autonomous SRE search has legitimately run out."""

    return (
        get_sre_retry_count(state) >= MAX_SRE_RETRIES
        or get_sre_repeated_failures(state) >= 1
    )


def assert_sre_retry_budget(
    state: dict[str, Any],
) -> None:
    """Refuse an SRE cycle that cannot be expected to converge.

    Reads persisted counters only, so restarting the CLI cannot quietly
    reopen the loop. Called before any provider call, so an exhausted budget
    costs nothing and the persisted evidence stays untouched.
    """

    if get_sre_repeated_failures(state) >= 1:
        raise NonConvergingSREError(
            "NON_CONVERGING_SRE: two consecutive SRE cycles produced the "
            "same failure. The workflow stopped instead of spending "
            "another provider call. Inspect the persisted SRE evidence, "
            "findings, blockers, observability readiness and incident "
            "readiness of the last attempt."
        )

    count = get_sre_retry_count(state)

    if count >= MAX_SRE_RETRIES:
        raise NonConvergingSREError(
            "NON_CONVERGING_SRE: operational validation is not converging: "
            f"{count} SRE cycles failed (limit {MAX_SRE_RETRIES}). The "
            "workflow stopped instead of spending another provider call. "
            "SRE does not modify the workspace, so a further attempt would "
            "evaluate the same product and operational state again."
        )
