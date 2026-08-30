from pathlib import Path
from typing import Any

from ai_factory.approvals import approve
from ai_factory.orchestrator import activate_next_agent
from ai_factory.transitions import set_agent_status


APPROVAL_AGENT_MAP = {
    "product_scope": "product",
    "design": "ux_ui",
    "architecture": "architect",
    "development": "developer",
    "qa": "qa",
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

    if approval_name == "development":
        development_gate = state.get(
            "development_gate"
        )

        if not isinstance(
            development_gate,
            dict,
        ):
            raise ValueError(
                "Project state does not contain a valid development_gate."
            )

        if (
            development_gate.get("status")
            != "READY_FOR_REVIEW"
        ):
            raise ValueError(
                "Development cannot be approved: "
                "the Development Gate is not ready for human approval."
            )

    if approval_name == "qa":
        qa_gate = state.get(
            "qa_gate"
        )

        if not isinstance(
            qa_gate,
            dict,
        ):
            raise ValueError(
                "Project state does not contain a valid qa_gate."
            )

        if (
            qa_gate.get("status")
            != "READY_FOR_REVIEW"
        ):
            raise ValueError(
                "QA cannot be approved: "
                "the QA Gate is not ready for human approval."
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

    if approval_name == "qa":
        qa_gate = state[
            "qa_gate"
        ]

        qa_gate[
            "human_approval"
        ] = True

        qa_gate[
            "status"
        ] = "APPROVED"

    if approval_name == "development":
        development_gate = state[
            "development_gate"
        ]

        development_gate[
            "human_approval"
        ] = True

        development_gate[
            "status"
        ] = "APPROVED"

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
