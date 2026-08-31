from typing import Any


AGENT_PHASES = {
    "product": "discovery",
    "ux_ui": "design",
    "architect": "architecture",
    "developer": "implementation",
    "qa": "qa",
    "security": "security",
    "devops": "devops",
    "sre": "sre",
}


def get_project_phase(
    state: dict[str, Any],
) -> str:
    """Derive the current project phase from workflow state."""

    agents = state.get("agents", {})

    for agent_name, phase in AGENT_PHASES.items():
        agent = agents.get(agent_name)

        if not isinstance(agent, dict):
            continue

        if agent.get("status") != "APPROVED":
            return phase

    production_gate = state.get(
        "production_gate",
        {},
    )

    if (
        isinstance(production_gate, dict)
        and production_gate.get("status") == "APPROVED"
    ):
        return "production"

    return "production"


def update_project_phase(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Update the persisted project phase from workflow state."""

    project = state.get(
        "project"
    )

    if not isinstance(
        project,
        dict,
    ):
        return state

    project["phase"] = get_project_phase(
        state
    )

    return state
