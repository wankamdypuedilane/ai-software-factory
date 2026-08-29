from pathlib import Path

from ai_factory.agent_runner import run_agent
from ai_factory.orchestrator import (
    get_execution_blocker,
    get_next_agent,
)
from ai_factory.providers import ModelProvider
from ai_factory.state import load_state


def run_next_agent(
    project_root: Path,
    provider: ModelProvider,
) -> tuple[str, str]:
    """Determine and execute the next agent in the project workflow."""

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)

    agent_name = get_next_agent(state)

    if agent_name is None:
        blocker = get_execution_blocker(state)

        if blocker:
            raise ValueError(
                "Execution blocked.\n"
                f"{blocker}"
            )

        raise ValueError(
            "No agent is currently ready for execution."
        )

    output = run_agent(
        project_root=project_root,
        agent_name=agent_name,
        provider=provider,
    )

    return agent_name, output
