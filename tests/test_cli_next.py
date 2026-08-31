from pathlib import Path

from ai_factory.cli import main
from ai_factory.orchestrator import get_next_agent
from ai_factory.state import save_state


def test_next_agent_is_product() -> None:
    state = {
        "agents": {
            "product": {"status": "READY"},
            "ux_ui": {"status": "NOT_STARTED"},
            "architect": {"status": "NOT_STARTED"},
            "developer": {"status": "NOT_STARTED"},
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        }
    }

    assert get_next_agent(state) == "product"


def test_cli_next_returns_none_for_completed_project(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
                "phase": "completed",
            },
            "approvals": {
                "product_scope": True,
                "design": True,
                "architecture": True,
                "development": True,
                "qa": True,
                "security": True,
                "devops": True,
                "sre": True,
                "production_deployment": True,
            },
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "APPROVED"},
                "devops": {"status": "APPROVED"},
                "sre": {"status": "APPROVED"},
            },
            "production_gate": {
                "status": "APPROVED",
                "reasons": [],
                "human_approval": True,
            },
        },
    )

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "next",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert output.strip() == "none"