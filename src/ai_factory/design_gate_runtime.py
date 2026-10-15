from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.blocker_contract import (
    blocker_messages,
    blocking_blockers,
    coerce_blockers,
)


def _unresolved_messages(
    gate: dict[str, Any],
    blockers: list[Any],
) -> list[str]:
    """Return blocking messages the human has not already resolved."""

    resolved = gate.get("resolved_blockers", [])

    if not isinstance(resolved, list):
        resolved = []

    return [
        message
        for message in blocker_messages(
            blocking_blockers(
                coerce_blockers(blockers)
            )
        )
        if message not in resolved
    ]


def update_design_gate_from_result(
    state: dict[str, Any],
    result: AgentResult,
    generated_paths: list[str],
) -> dict[str, Any]:
    """Update the Design Gate from a completed UX/UI result."""

    gate = state.get("design_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid design_gate."
        )

    requested_total = len(
        result.artifact_requests
    )

    generated_total = len(
        generated_paths
    )

    gate["groups"] = {
        "deliverables": {
            "approved": generated_total,
            "total": requested_total,
        }
    }

    unresolved = _unresolved_messages(
        gate,
        result.blockers,
    )

    gate["external_blockers"] = unresolved

    if (
        requested_total > 0
        and generated_total == requested_total
        and not unresolved
    ):
        gate["status"] = "READY_FOR_REVIEW"
    else:
        gate["status"] = "PARTIAL"

    gate["human_approval"] = False

    return state


def rebuild_design_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild the Design Gate from the persisted UX/UI result."""

    agents = state.get("agents", {})

    ux_ui = agents.get("ux_ui")

    if not isinstance(ux_ui, dict):
        raise ValueError(
            "Project state does not contain a valid ux_ui agent."
        )

    last_result = ux_ui.get("last_result")

    if not isinstance(last_result, dict):
        raise ValueError(
            "UX/UI does not contain a persisted result."
        )

    artifact_requests = last_result.get(
        "artifact_requests",
        [],
    )

    generated_paths = last_result.get(
        "generated_artifacts",
        [],
    )

    blockers = last_result.get(
        "blockers",
        [],
    )

    if not isinstance(artifact_requests, list):
        raise ValueError(
            "UX/UI artifact_requests must be a list."
        )

    if not isinstance(generated_paths, list):
        raise ValueError(
            "UX/UI generated_artifacts must be a list."
        )

    if not isinstance(blockers, list):
        raise ValueError(
            "UX/UI blockers must be a list."
        )

    gate = state.get("design_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid design_gate."
        )

    requested_total = len(artifact_requests)
    generated_total = len(generated_paths)

    gate["groups"] = {
        "deliverables": {
            "approved": generated_total,
            "total": requested_total,
        }
    }

    unresolved = _unresolved_messages(
        gate,
        blockers,
    )

    gate["external_blockers"] = unresolved

    deliverables_ready = (
        requested_total > 0
        and generated_total == requested_total
        and not unresolved
    )

    approvals = state.get(
        "approvals",
        {},
    )

    design_approved = (
        isinstance(approvals, dict)
        and approvals.get("design") is True
    )

    if deliverables_ready and design_approved:
        gate["status"] = "APPROVED"
        gate["human_approval"] = True
    elif deliverables_ready:
        gate["status"] = "READY_FOR_REVIEW"
        gate["human_approval"] = False
    else:
        gate["status"] = "PARTIAL"
        gate["human_approval"] = False

    return state
