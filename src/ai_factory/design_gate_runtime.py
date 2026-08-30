from typing import Any

from ai_factory.agent_result import AgentResult


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

    gate["external_blockers"] = list(
        result.blockers
    )

    if (
        requested_total > 0
        and generated_total == requested_total
        and not result.blockers
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

    gate["external_blockers"] = list(blockers)

    if (
        requested_total > 0
        and generated_total == requested_total
        and not blockers
    ):
        gate["status"] = "READY_FOR_REVIEW"
    else:
        gate["status"] = "PARTIAL"

    gate["human_approval"] = False

    return state
