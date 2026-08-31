from typing import Any


AGENT_ORDER = [
    "product",
    "ux_ui",
    "architect",
    "developer",
    "qa",
    "security",
    "devops",
    "sre",
]

REVIEW_GATE_CONFIG = {
    "qa": (
        "qa_gate",
        "QA",
        "QA Gate",
    ),
    "security": (
        "security_gate",
        "Security",
        "Security Gate",
    ),
    "devops": (
        "devops_gate",
        "DevOps",
        "DevOps Gate",
    ),
    "sre": (
        "sre_gate",
        "SRE",
        "SRE Gate",
    ),
}


def get_next_agent(state: dict[str, Any]) -> str | None:
    """Return the next agent that should work based on project state."""

    agents = state["agents"]

    for agent_name in AGENT_ORDER:
        status = agents[agent_name]["status"]

        if status in {"READY", "FAILED"}:
            return agent_name

        if status in {"BLOCKED", "REVIEW_REQUIRED"}:
            return None

    return None


def get_execution_blocker(
    state: dict[str, Any],
) -> str | None:
    """Return a human-readable reason why execution cannot continue."""

    agents = state.get("agents", {})

    for agent_name in AGENT_ORDER:
        agent = agents.get(agent_name)

        if not isinstance(agent, dict):
            continue

        status = agent.get("status")

        if status == "BLOCKED":
            return (
                f"Agent '{agent_name}' is blocked."
            )

        if status == "REVIEW_REQUIRED":
            if agent_name == "ux_ui":
                design_gate = state.get(
                    "design_gate",
                    {},
                )

                status_value = design_gate.get(
                    "status",
                    "UNKNOWN",
                )

                groups = design_gate.get(
                    "groups",
                    {},
                )

                external_blockers = design_gate.get(
                    "external_blockers",
                    [],
                )

                details = [
                    (
                        "UX/UI is waiting for "
                        "Design Gate completion."
                    ),
                    (
                        f"Design Gate status: "
                        f"{status_value}"
                    ),
                ]

                for group_name, group_data in groups.items():
                    approved = group_data.get(
                        "approved",
                        0,
                    )
                    total = group_data.get(
                        "total",
                        0,
                    )

                    details.append(
                        f"{group_name.capitalize()}: "
                        f"{approved}/{total}"
                    )

                if external_blockers:
                    details.append(
                        "External blockers: "
                        + ", ".join(
                            external_blockers
                        )
                    )

                return "\n".join(
                    details
                )

            if agent_name == "architect":
                technology_gate = state.get(
                    "technology_gate",
                    {},
                )

                status_value = technology_gate.get(
                    "status",
                    "UNKNOWN",
                )

                human_approval = (
                    "approved"
                    if technology_gate.get(
                        "human_approval",
                        False,
                    )
                    else "pending"
                )

                details = [
                    (
                        "Architect is waiting for "
                        "Technology Gate completion."
                    ),
                    (
                        f"Technology Gate status: "
                        f"{status_value}"
                    ),
                    (
                        f"Human approval: "
                        f"{human_approval}"
                    ),
                ]

                return "\n".join(
                    details
                )

            if agent_name == "developer":
                development_gate = state.get(
                    "development_gate",
                    {},
                )

                status_value = development_gate.get(
                    "status",
                    "UNKNOWN",
                )

                human_approval = development_gate.get(
                    "human_approval",
                    False,
                )

                approval_text = (
                    "approved"
                    if human_approval
                    else "pending"
                )

                return "\n".join(
                    [
                        "Developer is waiting for "
                        "Development Gate completion.",
                        "Development Gate status: "
                        f"{status_value}",
                        "Human approval: "
                        f"{approval_text}",
                    ]
                )

            gate_config = REVIEW_GATE_CONFIG.get(
                agent_name
            )

            if gate_config is not None:
                (
                    gate_key,
                    agent_label,
                    gate_label,
                ) = gate_config

                gate = state.get(
                    gate_key,
                    {},
                )

                status_value = gate.get(
                    "status",
                    "UNKNOWN",
                )

                human_approval = gate.get(
                    "human_approval",
                    False,
                )

                approval_text = (
                    "approved"
                    if human_approval
                    else "pending"
                )

                return "\n".join(
                    [
                        f"{agent_label} is waiting for "
                        f"{gate_label} completion.",
                        f"{gate_label} status: "
                        f"{status_value}",
                        "Human approval: "
                        f"{approval_text}",
                    ]
                )

            return (
                f"Agent '{agent_name}' "
                f"is waiting for human review."
            )

    return None


def activate_next_agent(
    state: dict[str, Any],
    completed_agent: str,
) -> dict[str, Any]:
    """Activate the agent that follows an approved agent."""

    try:
        current_index = AGENT_ORDER.index(
            completed_agent
        )
    except ValueError as error:
        raise ValueError(
            f"Unknown agent in execution order: "
            f"{completed_agent}"
        ) from error

    next_index = current_index + 1

    if next_index >= len(AGENT_ORDER):
        return state

    next_agent = AGENT_ORDER[
        next_index
    ]

    agents = state.get(
        "agents",
        {},
    )

    if next_agent not in agents:
        raise KeyError(
            f"Unknown next agent: "
            f"{next_agent}"
        )

    if (
        agents[next_agent]["status"]
        == "NOT_STARTED"
    ):
        agents[next_agent][
            "status"
        ] = "READY"

    return state
