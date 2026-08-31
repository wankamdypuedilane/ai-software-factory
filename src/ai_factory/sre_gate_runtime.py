from typing import Any

from ai_factory.sre_gate import (
    evaluate_sre_gate,
)


def update_sre_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted SRE Gate from SRE state."""

    agents = state.get(
        "agents",
        {},
    )

    sre = agents.get(
        "sre"
    )

    if not isinstance(
        sre,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid sre agent."
        )

    gate = state.get(
        "sre_gate"
    )

    if not isinstance(
        gate,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid sre_gate."
        )

    evaluation = evaluate_sre_gate(
        sre
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
