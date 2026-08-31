from pathlib import Path

from ai_factory.cli import main
from ai_factory.state import load_state, save_state


def test_cli_run_workflow_executes_until_human_review(
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
                "phase": "discovery",
            },
            "agents": {
                "product": {
                    "status": "READY",
                },
                "ux_ui": {
                    "status": "NOT_STARTED",
                },
                "architect": {
                    "status": "NOT_STARTED",
                },
                "developer": {
                    "status": "NOT_STARTED",
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
            "context": {
                "agents": {
                    "product": [],
                }
            },
            "ai": {
                "provider": "mock",
                "model": None,
                "settings": {
                    "temperature": None,
                    "max_output_tokens": None,
                },
            },
        },
    )

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "run-workflow",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert "Agent: product" in output
    assert "Status: COMPLETED" in output
    assert "Workflow stopped." in output
    assert "Agent 'product' is waiting for human review." in output

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert (
        state["agents"]["product"]["status"]
        == "REVIEW_REQUIRED"
    )

    assert (
        state["agents"]["ux_ui"]["status"]
        == "NOT_STARTED"
    )
