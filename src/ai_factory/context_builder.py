from pathlib import Path
from typing import Any

from ai_factory.agent_loader import load_agent_contract
from ai_factory.state import load_state


def load_context_artifacts(
    project_root: Path,
    project_config: dict[str, Any],
    agent_name: str,
) -> dict[str, str]:
    """Load context artifacts configured for a specific agent."""

    context = project_config.get("context", {})
    agents_context = context.get("agents", {})

    artifact_paths = agents_context.get(
        agent_name,
        [],
    )

    if not isinstance(artifact_paths, list):
        raise ValueError(
            f"Context artifacts for agent '{agent_name}' must be a list."
        )

    artifacts: dict[str, str] = {}

    for relative_path in artifact_paths:
        artifact_path = project_root / relative_path

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Context artifact not found: {relative_path}"
            )

        artifacts[relative_path] = artifact_path.read_text(
            encoding="utf-8",
        )

    return artifacts


def build_agent_context(
    project_root: Path,
    agent_name: str,
) -> dict[str, Any]:
    """Build the execution context required by an agent."""

    factory_dir = project_root / ".factory"

    state_path = factory_dir / "state.yaml"
    config_path = factory_dir / "project.yaml"

    state = load_state(state_path)
    project_config = load_state(config_path)
    contract = load_agent_contract(agent_name)

    artifacts = load_context_artifacts(
        project_root=project_root,
        project_config=project_config,
        agent_name=agent_name,
    )

    return {
        "agent_name": agent_name,
        "contract": contract,
        "project": project_config,
        "state": state,
        "artifacts": artifacts,
    }
