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
