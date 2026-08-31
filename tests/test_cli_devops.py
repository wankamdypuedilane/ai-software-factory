from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import (
    load_state,
    save_state,
)


def test_cli_approve_devops(
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
                "phase": "devops",
            },
            "approvals": {
                "product_scope": True,
                "design": True,
                "architecture": True,
                "development": True,
                "qa": True,
                "security": True,
                "devops": False,
                "production_deployment": False,
            },
            "agents": {
                "product": {"status": "APPROVED"},
                "ux_ui": {"status": "APPROVED"},
                "architect": {"status": "APPROVED"},
                "developer": {"status": "APPROVED"},
                "qa": {"status": "APPROVED"},
                "security": {"status": "APPROVED"},
                "devops": {
                    "status": "REVIEW_REQUIRED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
            "devops_gate": {
                "status": "READY_FOR_REVIEW",
                "reasons": [],
                "human_approval": False,
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "technology": {
                "selection_mode": "manual",
                "constraints": {},
                "selected": {},
            },
        },
    )

    monkeypatch.chdir(
        tmp_path
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "approve",
            "devops",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert (
        "Human approval recorded: devops"
        in output
    )

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert state["approvals"]["devops"] is True

    assert (
        state["devops_gate"]["status"]
        == "APPROVED"
    )

    assert (
        state["devops_gate"]["human_approval"]
        is True
    )

    assert (
        state["agents"]["devops"]["status"]
        == "APPROVED"
    )

    assert (
        state["agents"]["sre"]["status"]
        == "READY"
    )
