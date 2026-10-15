from pathlib import Path

import pytest

from ai_factory.agent_loader import load_agent_contract
from ai_factory.resources import (
    get_agents_dir,
    get_templates_dir,
)


def test_resources_resolve_agents_and_templates() -> None:
    assert (get_agents_dir() / "product" / "AGENT.md").is_file()
    assert (
        get_templates_dir() / "project" / "state.yaml"
    ).is_file()
    assert (
        get_templates_dir() / "project" / "inputs" / "product.md"
    ).is_file()


def test_resources_honor_factory_home_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = tmp_path / "agents" / "product" / "AGENT.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("custom contract", encoding="utf-8")

    monkeypatch.setenv("AI_FACTORY_HOME", str(tmp_path))

    assert load_agent_contract("product") == "custom contract"


def test_resources_reject_invalid_factory_home(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_FACTORY_HOME", str(tmp_path))

    with pytest.raises(FileNotFoundError, match="AI_FACTORY_HOME"):
        get_templates_dir()
