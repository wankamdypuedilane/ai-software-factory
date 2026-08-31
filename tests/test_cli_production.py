from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import (
    load_state,
    save_state,
)


def test_cli_approve_production_deployment(
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
                "phase": "production",
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
                "production_deployment": False,
            },
            "agents": {
                "sre": {
                    "status": "APPROVED",
                },
            },
            "sre_gate": {
                "status": "APPROVED",
                "reasons": [],
                "human_approval": True,
            },
            "production_gate": {
                "status": "READY_FOR_REVIEW",
                "reasons": [],
                "human_approval": False,
            },
        },
    )

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "approve",
            "production_deployment",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert (
        "Human approval recorded: "
        "production_deployment"
        in output
    )

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        state["approvals"][
            "production_deployment"
        ]
        is True
    )

    gate = state["production_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True

    assert (
        state["agents"]["sre"]["status"]
        == "APPROVED"
    )
