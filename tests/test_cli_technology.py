from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import save_state


def test_technology_status_displays_gate(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "project.yaml",
        {
            "technology": {
                "selection_mode": "recommend",
            }
        },
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "technology_gate": {
                "status": "NOT_STARTED",
                "human_approval": False,
                "proposal": {},
            }
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "technology",
            "status",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert "Selection mode:    recommend" in output
    assert "Gate status:       NOT_STARTED" in output
    assert "Human approval:    pending" in output
    assert "Gate approved:     no" in output
    assert "Proposal:           none" in output
