from pathlib import Path
from typing import Any

from ai_factory.context_builder import load_agent_input
from ai_factory.phases import (
    update_project_phase,
)
from ai_factory.transitions import resume_agent


def resume_agent_with_input(
    project_root: Path,
    state: dict[str, Any],
    project_config: dict[str, Any],
    agent_name: str,
) -> dict[str, Any]:
    """Resume a blocked agent when human input is available."""

    human_input = load_agent_input(
        project_root=project_root,
        project_config=project_config,
        agent_name=agent_name,
    )

    if human_input is None or not human_input.strip():
        raise ValueError(
            f"Human input is required to resume agent '{agent_name}'."
        )

    state = resume_agent(
        state,
        agent_name,
    )

    return update_project_phase(
        state
    )
