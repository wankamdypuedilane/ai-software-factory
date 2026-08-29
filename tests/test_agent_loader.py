import pytest

from ai_factory.agent_loader import (
    get_agent_contract_path,
    load_agent_contract,
)


def test_get_agent_contract_path_returns_existing_contract() -> None:
    contract_path = get_agent_contract_path("architect")

    assert contract_path.exists()
    assert contract_path.name == "AGENT.md"


def test_load_agent_contract_returns_text() -> None:
    contract = load_agent_contract("architect")

    assert isinstance(contract, str)
    assert contract.strip() != ""


def test_load_agent_contract_rejects_unknown_agent() -> None:
    with pytest.raises(
        FileNotFoundError,
        match="Agent contract not found",
    ):
        load_agent_contract("unknown-agent")


def test_load_agent_contract_supports_underscore_agent_name() -> None:
    contract = load_agent_contract("ux_ui")

    assert isinstance(contract, str)
    assert contract.strip() != ""
