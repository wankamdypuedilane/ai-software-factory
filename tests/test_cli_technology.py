from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import load_state, save_state


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


def test_technology_submit_updates_gate(
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

    proposal_path = tmp_path / "proposal.yaml"

    save_state(
        proposal_path,
        {
            "components": {
                "backend": {
                    "technology": "Example Backend",
                    "rationale": "Fits the project requirements.",
                }
            }
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "technology",
            "submit",
            "proposal.yaml",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert "Technology proposal submitted for human review." in output

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["technology_gate"]["status"]
        == "REVIEW_REQUIRED"
    )

    assert (
        updated_state["technology_gate"]["human_approval"]
        is False
    )

    assert (
        updated_state["technology_gate"]["proposal"]
        ["components"]["backend"]["technology"]
        == "Example Backend"
    )


def test_technology_approve_updates_gate(
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
                "status": "REVIEW_REQUIRED",
                "human_approval": False,
                "proposal": {
                    "components": {
                        "backend": {
                            "technology": "Example Backend",
                            "rationale": "Fits the project requirements.",
                        }
                    }
                },
            }
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "technology",
            "approve",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert "Technology proposal approved." in output

    updated_state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        updated_state["technology_gate"]["status"]
        == "APPROVED"
    )

    assert (
        updated_state["technology_gate"]["human_approval"]
        is True
    )
