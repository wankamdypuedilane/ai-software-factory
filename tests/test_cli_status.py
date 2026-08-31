from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import save_state


def test_cli_status_displays_full_workflow_state(
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
            "design_gate": {
                "status": "APPROVED",
                "groups": {},
                "external_blockers": [],
                "human_approval": True,
            },
            "technology_gate": {
                "status": "APPROVED",
                "human_approval": True,
            },
            "development_gate": {
                "status": "APPROVED",
                "reasons": [],
                "human_approval": True,
            },
            "qa_gate": {
                "status": "APPROVED",
                "reasons": [],
                "human_approval": True,
            },
            "security_gate": {
                "status": "APPROVED",
                "reasons": [],
                "human_approval": True,
            },
            "devops_gate": {
                "status": "APPROVED",
                "reasons": [],
                "human_approval": True,
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
            "status",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert "Project: Test Project" in output
    assert "Phase: production" in output

    assert "Design Gate:" in output
    assert "Workflow Gates:" in output

    assert "Technology Gate" in output
    assert "Development Gate" in output
    assert "QA Gate" in output
    assert "Security Gate" in output
    assert "DevOps Gate" in output
    assert "SRE Gate" in output
    assert "Production Gate" in output

    assert "READY_FOR_REVIEW" in output
    assert "pending" in output

    assert "Next agent: none" in output
