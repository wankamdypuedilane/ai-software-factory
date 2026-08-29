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
                design_gate = state.get("design_gate", {})

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
                    "UX/UI is waiting for Design Gate completion.",
                    f"Design Gate status: {status_value}",
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
                        + ", ".join(external_blockers)
                    )

                return "\n".join(details)

            return (
                f"Agent '{agent_name}' is waiting for human review."
            )

    return None
