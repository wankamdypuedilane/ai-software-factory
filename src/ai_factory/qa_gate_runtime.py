from typing import Any

from ai_factory.qa_gate import (
    evaluate_qa_gate,
)


def update_qa_gate_from_state(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted QA Gate from QA state."""

    agents = state.get(
        "agents",
        {},
    )

    qa = agents.get("qa")

    if not isinstance(qa, dict):
        raise ValueError(
            "Project state does not contain a valid QA agent."
        )

    gate = state.get("qa_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid qa_gate."
        )

    evaluation = evaluate_qa_gate(
        qa
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
