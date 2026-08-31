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
