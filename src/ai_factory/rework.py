"""Send validation defects back to the Developer.

QA, Security, DevOps and SRE never modify the workspace, and an approved
Developer is terminal. A real run therefore had no way out when QA found a
genuine defect in approved code: retrying QA re-validated the same files and
stopped as non-converging.

`rework` is the explicit, human-initiated path back. It reopens the Developer
with the validator's items as a rework request, and puts every validation
phase after the Developer back to NOT_STARTED, because each of them approved
code that is about to change. Nothing is deleted: the request and each
reopened budget are recorded in the state.
"""

from datetime import datetime, timezone
from typing import Any

from ai_factory.phases import update_project_phase
from ai_factory.replan_guard import BUDGET_FIELDS


# Validators whose result can be sent back, and where their items live in
# the persisted result.
REWORK_ITEM_FIELDS = {
    "qa": "qa_defects",
    "security": "security_findings",
    "devops": "devops_changes",
    "sre": "sre_findings",
}

REWORK_SOURCE_STATUSES = frozenset(
    {
        "FAILED",
        "BLOCKED",
        "REVIEW_REQUIRED",
    }
)

# Every phase that validates the Developer's output, in workflow order.
VALIDATION_AGENTS = (
    "qa",
    "security",
    "devops",
    "sre",
)

GATE_BY_AGENT = {
    "developer": "development_gate",
    "qa": "qa_gate",
    "security": "security_gate",
    "devops": "devops_gate",
    "sre": "sre_gate",
}

APPROVAL_BY_AGENT = {
    "developer": "development",
    "qa": "qa",
    "security": "security",
    "devops": "devops",
    "sre": "sre",
}

REWORK_FIELD = "rework"
REWORK_HISTORY_FIELD = "rework_history"


class ReworkError(ValueError):
    """The requested rework is not allowed in the current state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent(
    state: dict[str, Any],
    agent_name: str,
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict) or not isinstance(
        agents.get(agent_name),
        dict,
    ):
        raise ReworkError(
            f"Project state does not contain a valid {agent_name} agent."
        )

    return agents[agent_name]


def get_rework_items(
    state: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    """Return the items a validator reported in its last result."""

    field = REWORK_ITEM_FIELDS[source]
    last_result = _agent(state, source).get("last_result")

    if not isinstance(last_result, dict):
        return []

    items = last_result.get(field, [])

    if not isinstance(items, list):
        return []

    return [
        item
        for item in items
        if isinstance(item, dict)
    ]


def get_open_rework(
    state: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the rework request the Developer still has to address."""

    rework = state.get(REWORK_FIELD)

    if isinstance(rework, dict) and rework.get("status") == "OPEN":
        return rework

    return None


def _reset_gate(
    state: dict[str, Any],
    agent_name: str,
) -> None:
    gate = state.get(GATE_BY_AGENT[agent_name])

    if not isinstance(gate, dict):
        return

    gate["status"] = "NOT_STARTED"
    gate["reasons"] = []
    gate["human_approval"] = False


def _reset_budget(
    state: dict[str, Any],
    agent_name: str,
) -> dict[str, Any] | None:
    """Zero a budget the rework makes obsolete, and return its audit entry."""

    last_result = _agent(state, agent_name).get("last_result")

    if not isinstance(last_result, dict):
        return None

    count_field, repeated_field, signature_field = BUDGET_FIELDS[agent_name]

    previous = {
        count_field: last_result.get(count_field, 0),
        repeated_field: last_result.get(repeated_field, 0),
        signature_field: last_result.get(signature_field, ""),
    }

    last_result[count_field] = 0
    last_result[repeated_field] = 0
    last_result[signature_field] = ""

    return {
        "agent": agent_name,
        "previous": previous,
    }


def request_rework(
    state: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    """Send a validator's items back to the Developer.

    Allowed only from a validator that stopped (FAILED, BLOCKED or waiting for
    review) with at least one reported item, and only once the Developer has
    been approved: before that, the ordinary Developer retry applies.
    """

    if source not in REWORK_ITEM_FIELDS:
        raise ReworkError(
            f"Rework can only be requested from: "
            f"{', '.join(REWORK_ITEM_FIELDS)}."
        )

    source_status = _agent(state, source).get("status")

    if source_status not in REWORK_SOURCE_STATUSES:
        raise ReworkError(
            f"Rework from '{source}' requires it to be FAILED, BLOCKED or "
            f"REVIEW_REQUIRED; it is {source_status}."
        )

    developer = _agent(state, "developer")

    if developer.get("status") != "APPROVED":
        raise ReworkError(
            "Rework applies to approved development only. The Developer is "
            f"{developer.get('status')}: use 'retry developer' instead."
        )

    items = get_rework_items(state, source)

    if not items:
        raise ReworkError(
            f"'{source}' reported no item to fix. Rework needs at least one "
            "defect or finding to send back."
        )

    budget_resets: list[dict[str, Any]] = []

    # The Developer starts a new, explicitly requested cycle: its previous
    # task results would otherwise make the batch skip the units it now has
    # to change, and its previous failures do not belong to this request.
    developer_result = developer.get("last_result")

    if isinstance(developer_result, dict):
        developer_result["implementation_results"] = []
        developer_result["failed_task_id"] = None
        developer_result["implementation_test_failed"] = False
        developer_result["implementation_blocked"] = False
        developer_result["resume_from"] = None

        reset = _reset_budget(state, "developer")

        if reset:
            budget_resets.append(reset)

    developer["status"] = "READY"
    _reset_gate(state, "developer")

    approvals = state.get("approvals")

    if not isinstance(approvals, dict):
        raise ReworkError(
            "Project state does not contain valid approvals."
        )

    approvals["development"] = False

    # Every validation approved code that is about to change.
    for agent_name in VALIDATION_AGENTS:
        agent = _agent(state, agent_name)
        agent["status"] = "NOT_STARTED"
        approvals[APPROVAL_BY_AGENT[agent_name]] = False
        _reset_gate(state, agent_name)

        reset = _reset_budget(state, agent_name)

        if reset:
            budget_resets.append(reset)

    approvals["production_deployment"] = False

    production_gate = state.get("production_gate")

    if isinstance(production_gate, dict):
        production_gate["status"] = "NOT_STARTED"
        production_gate["reasons"] = []
        production_gate["human_approval"] = False

    request = {
        "status": "OPEN",
        "source": source,
        "items": items,
        "requested_at": _now(),
        "budget_resets": budget_resets,
    }

    state[REWORK_FIELD] = request

    history = state.get(REWORK_HISTORY_FIELD)

    if not isinstance(history, list):
        history = []

    history.append(
        {
            "source": source,
            "item_ids": [
                item.get("id")
                for item in items
            ],
            "requested_at": request["requested_at"],
        }
    )

    state[REWORK_HISTORY_FIELD] = history

    return update_project_phase(state)


def mark_rework_addressed(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Record that a Developer cycle completed against the open request."""

    rework = get_open_rework(state)

    if rework is not None:
        rework["status"] = "ADDRESSED"
        rework["addressed_at"] = _now()

    return state


def format_rework_request(
    rework: dict[str, Any],
) -> list[str]:
    """Render an open rework request for a Developer prompt."""

    source = rework.get("source", "validation")

    lines = [
        f"The approved implementation was sent back by {source} with the "
        "items below.",
        "Fix every item in the existing code. Change only what the items "
        "require and keep every other behavior and interface unchanged.",
        "Add or update a test that fails before the fix and passes after it "
        "for each item.",
    ]

    for item in rework.get("items", []):
        if not isinstance(item, dict):
            continue

        details = ", ".join(
            f"{key}: {value}"
            for key, value in item.items()
            if value not in (None, "", [])
        )

        lines.append(f"- {details}")

    return lines
