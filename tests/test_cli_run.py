from pathlib import Path

import pytest

from ai_factory.cli import main
from ai_factory.state import save_state


def test_cli_run_rejects_completed_project(
    tmp_path: Path,
    monkeypatch,
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

    save_state(
        factory_dir / "project.yaml",
        {
            "provider": {
                "type": "mock",
            },
        },
    )

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "run",
        ],
    )

    with pytest.raises(SystemExit):
        main()