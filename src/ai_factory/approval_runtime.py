from typing import Any

from ai_factory.approvals import approve
from ai_factory.transitions import set_agent_status


APPROVAL_AGENT_MAP = {
    "product_scope": "product",
    "design": "ux_ui",
    "architecture": "architect",
}


def apply_approval(
    state: dict[str, Any],
    approval_name: str,
) -> dict[str, Any]:
    """Apply a human approval and advance its owning agent."""

    state = approve(
        state,
        approval_name,
    )

    agent_name = APPROVAL_AGENT_MAP.get(
        approval_name,
    )

    if agent_name is None:
        return state

    agents = state.get("agents", {})

    if agent_name not in agents:
        raise KeyError(
            f"Unknown agent: {agent_name}"
        )

    current_status = agents[agent_name]["status"]

    if current_status != "REVIEW_REQUIRED":
        raise ValueError(
            f"Agent '{agent_name}' is not waiting for review."
        )

    return set_agent_status(
        state,
        agent_name,
        "APPROVED",
    )
