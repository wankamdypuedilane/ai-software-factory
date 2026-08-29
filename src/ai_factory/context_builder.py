from pathlib import Path
from typing import Any

from ai_factory.agent_loader import load_agent_contract
from ai_factory.state import load_state


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

    return {
        "agent_name": agent_name,
        "contract": contract,
        "project": project_config,
        "state": state,
    }
