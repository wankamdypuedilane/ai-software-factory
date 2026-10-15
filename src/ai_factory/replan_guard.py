"""Bound on Developer replanning cycles.

A failing implementation unit is retried inside its own execution. When that
does not converge, the Developer agent is asked to replan, which costs a
provider call every time. Nothing bounded that cycle, so a single defect
could consume provider calls indefinitely.
"""

from datetime import datetime, timezone
from typing import Any


MAX_DEVELOPER_REPLANS = 3

# Agents whose retry cycle is budgeted. Only these can have a budget
# reopened, because only these have a budget at all. Each entry names the
# persisted fields that hold its counters, so the operator reset - its
# eligibility rules, its audit trail, its CLI flag - is written once instead
# of once per agent.
BUDGET_FIELDS = {
    "developer": (
        "replan_count",
        "repeated_failures",
        "failure_signature",
    ),
    "qa": (
        "qa_retry_count",
        "qa_repeated_failures",
        "qa_failure_signature",
    ),
    "security": (
        "security_retry_count",
        "security_repeated_failures",
        "security_failure_signature",
    ),
    "devops": (
        "devops_retry_count",
        "devops_repeated_failures",
        "devops_failure_signature",
    ),
    "sre": (
        "sre_retry_count",
        "sre_repeated_failures",
        "sre_failure_signature",
    ),
}

BUDGETED_AGENTS = frozenset(BUDGET_FIELDS)

RESET_HISTORY_FIELD = "replan_budget_resets"


class NonConvergingImplementationError(ValueError):
    """The Developer keeps replanning without making progress."""


class ReplanBudgetResetError(ValueError):
    """The operator asked to reopen a budget that may not be reopened."""


def get_agent_result(
    state: dict[str, Any],
    agent_name: str,
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict):
        return {}

    agent = agents.get(agent_name)

    if not isinstance(agent, dict):
        return {}

    last_result = agent.get("last_result")

    return last_result if isinstance(last_result, dict) else {}


def get_developer_result(
    state: dict[str, Any],
) -> dict[str, Any]:
    return get_agent_result(state, "developer")


def get_budget_counters(
    state: dict[str, Any],
    agent_name: str,
) -> tuple[int, int, str]:
    """Return (retries, repeated failures, signature) for a budgeted agent."""

    count_field, repeated_field, signature_field = BUDGET_FIELDS[agent_name]

    last_result = get_agent_result(state, agent_name)

    count = last_result.get(count_field)
    repeated = last_result.get(repeated_field)
    signature = last_result.get(signature_field)

    return (
        count if isinstance(count, int) and count > 0 else 0,
        repeated if isinstance(repeated, int) and repeated > 0 else 0,
        signature if isinstance(signature, str) else "",
    )


def get_replan_count(
    state: dict[str, Any],
) -> int:
    """Return how many replanning cycles already failed.

    The count lives in the persisted result, so restarting the CLI cannot
    quietly reopen an unbounded loop.
    """

    value = get_developer_result(state).get("replan_count")

    return value if isinstance(value, int) and value > 0 else 0


def get_failure_signature(
    state: dict[str, Any],
) -> str:
    value = get_developer_result(state).get("failure_signature")

    return value if isinstance(value, str) else ""


def get_repeated_failures(
    state: dict[str, Any],
) -> int:
    """Return how many times the same failure repeated consecutively.

    Computed when a cycle ends, where both the previous and the new
    signature are known. The guard runs before a cycle exists, so it can
    only read this counter - it can never derive it.
    """

    value = get_developer_result(state).get("repeated_failures")

    return value if isinstance(value, int) and value > 0 else 0


def build_failure_signature(
    last_result: dict[str, Any],
) -> str:
    """Describe how a cycle failed, from structured fields only.

    The task identifier is deliberately excluded: the agent renames the unit
    on every replan, so including it would make every cycle look new.
    """

    parts: list[str] = []

    if last_result.get("implementation_blocked") is True:
        parts.append("blocked")

    if last_result.get("implementation_test_failed") is True:
        parts.append("test_failed")

    failed_commands = sorted(
        {
            item.get("command")
            for item in last_result.get("test_results", []) or []
            if (
                isinstance(item, dict)
                and item.get("passed") is False
                and isinstance(item.get("command"), str)
            )
        }
    )

    parts.extend(failed_commands)

    return "|".join(parts)


def next_replan_count(
    previous: int,
    failed: bool,
) -> int:
    """Advance the counter: a successful cycle closes it."""

    if not failed:
        return 0

    return previous + 1


def next_repeated_failures(
    previous_repeated: int,
    previous_signature: str,
    new_signature: str,
) -> int:
    """Advance the repetition counter across two distinct cycles.

    Called when a cycle ends: `previous_signature` belongs to the cycle
    before it, `new_signature` to the one that just finished. A cycle that
    succeeded carries an empty signature and clears the history.
    """

    if not new_signature:
        return 0

    if previous_signature and previous_signature == new_signature:
        return previous_repeated + 1

    return 0


def budget_limit(
    agent_name: str,
) -> int:
    """Return the autonomous cycle limit of a budgeted agent."""

    if agent_name == "qa":
        from ai_factory.qa_retry_guard import MAX_QA_RETRIES

        return MAX_QA_RETRIES

    if agent_name == "security":
        from ai_factory.security_retry_guard import (
            MAX_SECURITY_RETRIES,
        )

        return MAX_SECURITY_RETRIES

    if agent_name == "devops":
        from ai_factory.devops_retry_guard import MAX_DEVOPS_RETRIES

        return MAX_DEVOPS_RETRIES

    if agent_name == "sre":
        from ai_factory.sre_retry_guard import MAX_SRE_RETRIES

        return MAX_SRE_RETRIES

    return MAX_DEVELOPER_REPLANS


def is_budget_exhausted(
    state: dict[str, Any],
    agent_name: str = "developer",
) -> bool:
    """Whether an agent's autonomous search has legitimately run out."""

    count, repeated, _ = get_budget_counters(state, agent_name)

    return (
        count >= budget_limit(agent_name)
        or repeated >= 1
    )


def reset_replan_budget(
    state: dict[str, Any],
    agent_name: str = "developer",
    source: str = "operator",
) -> dict[str, Any]:
    """Deliberately authorize a new bounded replanning window.

    This is an explicit operator act, never a side effect of an ordinary
    retry: otherwise repeated retries would recreate the unbounded loop the
    budget exists to prevent.

    It reopens the search. It does not delete the evidence of why the
    previous search stopped: diagnostics, failed task and results are kept.
    """

    if agent_name not in BUDGETED_AGENTS:
        raise ReplanBudgetResetError(
            f"Agent '{agent_name}' has no replanning budget to reset. "
            f"Budgeted agents: {', '.join(sorted(BUDGETED_AGENTS))}."
        )

    agents = state.get("agents")

    if not isinstance(agents, dict) or agent_name not in agents:
        raise ReplanBudgetResetError(
            f"Unknown agent: {agent_name}"
        )

    agent = agents[agent_name]
    status = agent.get("status")

    if status != "FAILED":
        raise ReplanBudgetResetError(
            f"Agent '{agent_name}' must be FAILED to reopen its replanning "
            f"budget; it is {status}. A running or approved agent is never "
            "reset."
        )

    count, repeated, signature = get_budget_counters(
        state,
        agent_name,
    )

    if not is_budget_exhausted(state, agent_name):
        raise ReplanBudgetResetError(
            f"Agent '{agent_name}' still has replanning budget "
            f"({count}/{budget_limit(agent_name)}, "
            f"repeated failures {repeated}). "
            "Use an ordinary retry."
        )

    last_result = get_agent_result(state, agent_name)

    history = agent.get(RESET_HISTORY_FIELD)

    if not isinstance(history, list):
        history = []

    history.append(
        {
            "at": datetime.now(timezone.utc).isoformat(
                timespec="seconds",
            ),
            "previous_replan_count": count,
            "previous_repeated_failures": repeated,
            "previous_failure_signature": signature,
            "source": source,
        }
    )

    agent[RESET_HISTORY_FIELD] = history

    count_field, repeated_field, signature_field = BUDGET_FIELDS[
        agent_name
    ]

    last_result[count_field] = 0
    last_result[repeated_field] = 0
    last_result[signature_field] = ""

    agent["status"] = "READY"

    return state


def assert_replan_budget(
    state: dict[str, Any],
) -> None:
    """Refuse to start another cycle that cannot be expected to converge.

    Reads persisted counters only, so it is structurally incapable of
    comparing a stored value with itself. Called before any provider call,
    so an exhausted budget costs nothing.
    """

    count = get_replan_count(state)

    if get_repeated_failures(state) >= 1:
        raise NonConvergingImplementationError(
            "NON_CONVERGING_IMPLEMENTATION: two consecutive Developer "
            "cycles produced the same failure. The workflow stopped "
            "instead of spending another provider call. Inspect the "
            "persisted diagnostics of the last attempt."
        )

    if count >= MAX_DEVELOPER_REPLANS:
        raise NonConvergingImplementationError(
            "Developer implementation is not converging: "
            f"{count} replanning cycles failed "
            f"(limit {MAX_DEVELOPER_REPLANS}). The workflow stopped "
            "instead of spending another provider call. Inspect the "
            "persisted diagnostics of the last attempt."
        )
