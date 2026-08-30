from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import (
    load_state,
    save_state,
)


def test_cli_approve_development(
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
                "phase": "implementation",
            },
            "approvals": {
                "product_scope": True,
                "design": True,
                "architecture": True,
                "development": False,
                "production_deployment": False,
            },
            "agents": {
                "product": {
                    "status": "APPROVED",
                },
                "ux_ui": {
                    "status": "APPROVED",
                },
                "architect": {
                    "status": "APPROVED",
                },
                "developer": {
                    "status": "REVIEW_REQUIRED",
                },
                "qa": {
                    "status": "NOT_STARTED",
                },
                "security": {
                    "status": "NOT_STARTED",
                },
                "devops": {
                    "status": "NOT_STARTED",
                },
                "sre": {
                    "status": "NOT_STARTED",
                },
            },
            "development_gate": {
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
            "development",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert (
        "Human approval recorded: development"
        in output
    )

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert state["approvals"]["development"] is True

    assert (
        state["development_gate"]["status"]
        == "APPROVED"
    )

    assert (
        state["development_gate"]["human_approval"]
        is True
    )

    assert (
        state["agents"]["developer"]["status"]
        == "APPROVED"
    )

    assert (
        state["agents"]["qa"]["status"]
        == "READY"
    )
