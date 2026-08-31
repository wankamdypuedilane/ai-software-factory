from pathlib import Path
from typing import Any

from ai_factory.approvals import approve
from ai_factory.orchestrator import activate_next_agent
from ai_factory.phases import (
    update_project_phase,
)
from ai_factory.production_gate_runtime import (
    update_production_gate_from_state,
)
from ai_factory.transitions import set_agent_status


APPROVAL_AGENT_MAP = {
    "product_scope": "product",
    "design": "ux_ui",
    "architecture": "architect",
    "development": "developer",
    "qa": "qa",
    "security": "security",
    "devops": "devops",
    "sre": "sre",
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

    if approval_name == "production_deployment":
        production_gate = state.get(
            "production_gate"
        )

        if not isinstance(
            production_gate,
            dict,
        ):
            raise ValueError(
                "Project state does not contain a valid production_gate."
            )

        if (
            production_gate.get("status")
            != "READY_FOR_REVIEW"
        ):
            raise ValueError(
                "Production deployment cannot be approved: "
                "the Production Gate is not ready for human approval."
            )

        state = approve(
            state,
            approval_name,
        )

        production_gate[
            "human_approval"
        ] = True

        production_gate[
            "status"
        ] = "APPROVED"

        state = update_project_phase(
            state
        )

        return state

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

    if approval_name == "security":
        security_gate = state.get(
            "security_gate"
        )

        if not isinstance(
            security_gate,
            dict,
        ):
            raise ValueError(
                "Project state does not contain a valid security_gate."
            )

        if (
            security_gate.get("status")
            != "READY_FOR_REVIEW"
        ):
            raise ValueError(
                "Security cannot be approved: "
                "the Security Gate is not ready for human approval."
            )

    if approval_name == "devops":
        devops_gate = state.get(
            "devops_gate"
        )

        if not isinstance(
            devops_gate,
            dict,
        ):
            raise ValueError(
                "Project state does not contain a valid devops_gate."
            )

        if (
            devops_gate.get("status")
            != "READY_FOR_REVIEW"
        ):
            raise ValueError(
                "DevOps cannot be approved: "
                "the DevOps Gate is not ready for human approval."
            )

    if approval_name == "sre":
        sre_gate = state.get(
            "sre_gate"
        )

        if not isinstance(
            sre_gate,
            dict,
        ):
            raise ValueError(
                "Project state does not contain a valid sre_gate."
            )

        if (
            sre_gate.get("status")
            != "READY_FOR_REVIEW"
        ):
            raise ValueError(
                "SRE cannot be approved: "
                "the SRE Gate is not ready for human approval."
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

    if approval_name == "sre":
        sre_gate = state[
            "sre_gate"
        ]

        sre_gate[
            "human_approval"
        ] = True

        sre_gate[
            "status"
        ] = "APPROVED"

        if isinstance(
            state.get("production_gate"),
            dict,
        ):
            state = update_production_gate_from_state(
                state
            )

    if approval_name == "devops":
        devops_gate = state[
            "devops_gate"
        ]

        devops_gate[
            "human_approval"
        ] = True

        devops_gate[
            "status"
        ] = "APPROVED"

    if approval_name == "security":
        security_gate = state[
            "security_gate"
        ]

        security_gate[
            "human_approval"
        ] = True

        security_gate[
            "status"
        ] = "APPROVED"

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

    state = activate_next_agent(
        state,
        agent_name,
    )

    state = update_project_phase(
        state
    )

    return state
