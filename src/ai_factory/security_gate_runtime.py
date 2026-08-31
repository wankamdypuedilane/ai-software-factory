from typing import Any

from ai_factory.security_gate import (
    evaluate_security_gate,
)


def update_security_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted Security Gate from Security state."""

    agents = state.get(
        "agents",
        {},
    )

    security = agents.get(
        "security"
    )

    if not isinstance(
        security,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid security agent."
        )

    gate = state.get(
        "security_gate"
    )

    if not isinstance(
        gate,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid security_gate."
        )

    evaluation = evaluate_security_gate(
        security
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
