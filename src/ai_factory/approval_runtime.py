from pathlib import Path
from typing import Any

from ai_factory.approvals import approve
from ai_factory.orchestrator import activate_next_agent
from ai_factory.transitions import set_agent_status


APPROVAL_AGENT_MAP = {
    "product_scope": "product",
    "design": "ux_ui",
    "architecture": "architect",
}


def apply_approval(
    state: dict[str, Any],
    approval_name: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Apply a human approval and advance its owning agent."""

    agent_name = APPROVAL_AGENT_MAP.get(
        approval_name,
    )

    if agent_name is None:
        return approve(
            state,
            approval_name,
        )

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

    state = set_agent_status(
        state,
        agent_name,
        "APPROVED",
        project_root=project_root,
    )

    state = approve(
        state,
        approval_name,
    )

    if approval_name == "design":
        design_gate = state.get("design_gate")

        if not isinstance(design_gate, dict):
            raise ValueError(
                "Project state does not contain a valid design_gate."
            )

        design_gate["human_approval"] = True
        design_gate["status"] = "APPROVED"

    return activate_next_agent(
        state,
        agent_name,
    )
