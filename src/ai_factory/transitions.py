from typing import Any


VALID_STATUSES = {
    "NOT_STARTED",
    "READY",
    "IN_PROGRESS",
    "BLOCKED",
    "REVIEW_REQUIRED",
    "APPROVED",
    "FAILED",
    "COMPLETED",
}


def set_agent_status(
    state: dict[str, Any],
    agent_name: str,
    status: str,
) -> dict[str, Any]:
    """Update the status of an agent in project state."""

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    agents = state.get("agents", {})

    if agent_name not in agents:
        raise KeyError(f"Unknown agent: {agent_name}")

    agents[agent_name]["status"] = status

    return state