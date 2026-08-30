from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import load_state, save_state


def test_cli_design_rebuild(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "agents": {
                "ux_ui": {
                    "status": "REVIEW_REQUIRED",
                    "last_result": {
                        "artifact_requests": [
                            {
                                "path": "design/ux-ui/user-flows.md",
                                "purpose": "Document user flows.",
                            },
                            {
                                "path": "design/ux-ui/screen-specs.md",
                                "purpose": "Document screen specs.",
                            },
                        ],
                        "generated_artifacts": [
                            "design/ux-ui/user-flows.md",
                            "design/ux-ui/screen-specs.md",
                        ],
                        "blockers": [],
                    },
                }
            },
            "design_gate": {
                "status": "NOT_STARTED",
                "groups": {},
                "external_blockers": [],
                "human_approval": False,
            },
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "design",
            "rebuild",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert (
        "Design Gate rebuilt from persisted UX/UI results."
        in output
    )

    state = load_state(
        factory_dir / "state.yaml"
    )

    gate = state["design_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["groups"]["deliverables"] == {
        "approved": 2,
        "total": 2,
    }
    assert gate["human_approval"] is False
