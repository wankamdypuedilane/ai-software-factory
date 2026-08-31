from typing import Any

from ai_factory.devops_gate import (
    evaluate_devops_gate,
)


def update_devops_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted DevOps Gate from DevOps state."""

    agents = state.get(
        "agents",
        {},
    )

    devops = agents.get(
        "devops"
    )

    if not isinstance(
        devops,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid devops agent."
        )

    gate = state.get(
        "devops_gate"
    )

    if not isinstance(
        gate,
        dict,
    ):
        raise ValueError(
            "Project state does not contain a valid devops_gate."
        )

    evaluation = evaluate_devops_gate(
        devops
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
