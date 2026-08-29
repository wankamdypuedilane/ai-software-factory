from pathlib import Path
from typing import Any

from ai_factory.validators import validate_ux_ui_artifacts
from ai_factory.workflow import is_transition_allowed


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
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Update an agent status if the workflow transition is allowed."""

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    agents = state.get("agents", {})

    if agent_name not in agents:
        raise KeyError(f"Unknown agent: {agent_name}")

    current_status = agents[agent_name]["status"]

    if not is_transition_allowed(current_status, status):
        raise ValueError(
            f"Transition not allowed: "
            f"{agent_name} {current_status} -> {status}"
        )

    if agent_name == "ux_ui" and status == "REVIEW_REQUIRED":
        if project_root is None:
            raise ValueError(
                "Project root is required to validate UX/UI artifacts."
            )

        missing_artifacts = validate_ux_ui_artifacts(project_root)

        if missing_artifacts:
            missing_list = "\n".join(
                f"- {artifact}" for artifact in missing_artifacts
            )

            raise ValueError(
                "UX/UI artifacts are incomplete.\n"
                f"Missing artifacts:\n{missing_list}"
            )

    agents[agent_name]["status"] = status

    return state