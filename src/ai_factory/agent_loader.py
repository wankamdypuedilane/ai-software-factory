from pathlib import Path


def get_agents_root() -> Path:
    """Return the root directory containing agent contracts."""

    return (
        Path(__file__).resolve().parents[2]
        / "agents"
    )


def get_agent_contract_path(agent_name: str) -> Path:
    """Return the AGENT.md path for a given agent."""

    directory_name = agent_name.replace(
        "_",
        "-",
    )

    contract_path = (
        get_agents_root()
        / directory_name
        / "AGENT.md"
    )

    if not contract_path.exists():
        raise FileNotFoundError(
            f"Agent contract not found: {agent_name}"
        )

    return contract_path


def load_agent_contract(agent_name: str) -> str:
    """Load an agent contract as text."""

    contract_path = get_agent_contract_path(
        agent_name
    )

    return contract_path.read_text(
        encoding="utf-8",
    )
