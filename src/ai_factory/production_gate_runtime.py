from typing import Any

from ai_factory.production_gate import (
    evaluate_production_gate,
)


def update_production_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted Production Gate from project state."""

    gate = state.get(
        "production_gate"
    )

    if not isinstance(
        gate,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid production_gate."
        )

    if (
        gate.get("status") == "APPROVED"
        and gate.get("human_approval") is True
    ):
        return state

    evaluation = evaluate_production_gate(
        state
    )

    gate["reasons"] = list(
        evaluation.reasons
    )

    gate["human_approval"] = False

    if evaluation.ready:
        gate["status"] = "READY_FOR_REVIEW"
    else:
        gate["status"] = "NOT_READY"

    return state
