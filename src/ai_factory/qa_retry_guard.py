"""Bound on QA retry cycles.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. The Developer is bounded by
`assert_replan_budget`; QA was not, so a QA agent that kept failing was
selected again, called the provider again, and failed again without limit.

QA is bounded more tightly than the Developer, and for a structural reason
rather than a preference: a Developer replan rewrites the product, so the
next cycle validates something new, while QA never writes to the workspace.
A repeated QA cycle re-validates identical artifacts with an identical
prompt, so the second attempt is already close to the useful limit and a
third has nothing new to work with. The bound is therefore 2.

Only the pure counter arithmetic is shared with the Developer guard: those
functions take plain values rather than state, so reusing them duplicates no
key paths and changes no Developer behaviour.
"""

from typing import Any

from ai_factory.rework import recovery_guidance

from ai_factory.qa_evidence import (
    describe_qa_evidence,
    qa_evidence_satisfied,
)
from ai_factory.replan_guard import (
    next_repeated_failures,
    next_replan_count,
)


MAX_QA_RETRIES = 2

QA_RETRY_COUNT_FIELD = "qa_retry_count"
QA_REPEATED_FAILURES_FIELD = "qa_repeated_failures"
QA_FAILURE_SIGNATURE_FIELD = "qa_failure_signature"


class NonConvergingQAError(ValueError):
    """QA keeps failing without converging."""


def get_qa_result(
    state: dict[str, Any],
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict):
        return {}

    qa = agents.get("qa")

    if not isinstance(qa, dict):
        return {}

    last_result = qa.get("last_result")

    return last_result if isinstance(last_result, dict) else {}


def _counter(
    state: dict[str, Any],
    field: str,
) -> int:
    value = get_qa_result(state).get(field)

    return value if isinstance(value, int) and value > 0 else 0


def get_qa_retry_count(
    state: dict[str, Any],
) -> int:
    """How many QA cycles already failed, from persisted state only."""

    return _counter(state, QA_RETRY_COUNT_FIELD)


def get_qa_repeated_failures(
    state: dict[str, Any],
) -> int:
    return _counter(state, QA_REPEATED_FAILURES_FIELD)


def get_qa_failure_signature(
    state: dict[str, Any],
) -> str:
    value = get_qa_result(state).get(QA_FAILURE_SIGNATURE_FIELD)

    return value if isinstance(value, str) else ""


def build_qa_failure_signature(
    qa_last_result: dict[str, Any],
) -> str:
    """Describe how a QA cycle failed, from structured evidence only.

    The engine's own reason codes and the failing command strings are the
    stable parts. Summaries, defect titles and expected/actual text are the
    model's wording and are excluded, as are defect identifiers: the agent
    renumbers them between cycles, exactly as the Developer renames tasks.
    """

    test_results = qa_last_result.get("qa_test_results")
    test_results = test_results if isinstance(test_results, list) else []

    defects = qa_last_result.get("qa_defects")
    defects = defects if isinstance(defects, list) else []

    evidence = describe_qa_evidence(
        test_results=test_results,
        blockers=qa_last_result.get("qa_blockers", []),
        defects=defects,
    )

    model_passed = qa_last_result.get("qa_model_passed") is True

    if qa_evidence_satisfied(evidence) and model_passed:
        return ""

    parts: list[str] = []

    if evidence.executed_checks < 1:
        parts.append("no_evidence")

    if evidence.failed_checks:
        parts.append("failed_checks")

    if evidence.blocking_blockers:
        parts.append(f"blocking_blockers:{evidence.blocking_blockers}")

    if evidence.blocking_defects:
        parts.append(f"blocking_defects:{evidence.blocking_defects}")

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


def advance_qa_retry_state(
    qa_last_result: dict[str, Any],
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
        build_qa_failure_signature(qa_last_result)
        if cycle_failed
        else ""
    )

    qa_last_result[QA_RETRY_COUNT_FIELD] = next_replan_count(
        previous_count,
        failed=cycle_failed,
    )

    qa_last_result[QA_FAILURE_SIGNATURE_FIELD] = signature

    qa_last_result[QA_REPEATED_FAILURES_FIELD] = next_repeated_failures(
        previous_repeated,
        previous_signature,
        signature,
    )


def is_qa_budget_exhausted(
    state: dict[str, Any],
) -> bool:
    """Whether the autonomous QA search has legitimately run out."""

    return (
        get_qa_retry_count(state) >= MAX_QA_RETRIES
        or get_qa_repeated_failures(state) >= 1
    )


def assert_qa_retry_budget(
    state: dict[str, Any],
) -> None:
    """Refuse to start a QA cycle that cannot be expected to converge.

    Reads persisted counters only, so restarting the CLI cannot quietly
    reopen the loop. Called before any provider call, so an exhausted budget
    costs nothing.
    """

    if get_qa_repeated_failures(state) >= 1:
        raise NonConvergingQAError(
            "NON_CONVERGING_QA: two consecutive QA cycles produced the "
            "same failure. The workflow stopped instead of spending "
            "another provider call. Inspect the persisted QA evidence, "
            "defects and blockers of the last attempt."
            + recovery_guidance("qa")
        )

    count = get_qa_retry_count(state)

    if count >= MAX_QA_RETRIES:
        raise NonConvergingQAError(
            "NON_CONVERGING_QA: QA validation is not converging: "
            f"{count} QA cycles failed (limit {MAX_QA_RETRIES}). The "
            "workflow stopped instead of spending another provider call. "
            "QA does not modify the workspace, so a further attempt would "
            "validate the same artifacts again."
            + recovery_guidance("qa")
        )
