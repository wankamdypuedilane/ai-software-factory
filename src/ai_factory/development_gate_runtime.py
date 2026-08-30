from typing import Any

from ai_factory.development_gate import (
    evaluate_development_gate,
)


def update_development_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted Development Gate from Developer state."""

    agents = state.get("agents", {})

    developer = agents.get("developer")

    if not isinstance(developer, dict):
        raise ValueError(
            "Project state does not contain a valid developer agent."
        )

    gate = state.get("development_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid development_gate."
        )

    evaluation = evaluate_development_gate(
        developer
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
