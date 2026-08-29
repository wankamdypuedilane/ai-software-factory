from pathlib import Path

import pytest

from ai_factory.providers import MockProvider
from ai_factory.runtime import run_next_agent
from ai_factory.state import save_state


def test_run_next_agent_executes_selected_agent(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "product": {
                    "status": "COMPLETED",
                },
                "ux_ui": {
                    "status": "COMPLETED",
                },
                "architect": {
                    "status": "READY",
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
                    "architect": [],
                }
            },
        },
    )

    provider = MockProvider()

    agent_name, output = run_next_agent(
        project_root=tmp_path,
        provider=provider,
    )

    assert agent_name == "architect"

    assert output == (
        "Mock execution completed for agent: architect"
    )


def test_run_next_agent_rejects_when_no_agent_is_ready(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "agents": {
                "product": {
                    "status": "APPROVED",
                },
                "ux_ui": {
                    "status": "REVIEW_REQUIRED",
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

    provider = MockProvider()

    with pytest.raises(
        ValueError,
        match="Execution blocked",
    ):
        run_next_agent(
            project_root=tmp_path,
            provider=provider,
        )


from ai_factory.cli import main


def test_cli_run_executes_next_agent(
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
            },
            "agents": {
                "product": {
                    "status": "COMPLETED",
                },
                "ux_ui": {
                    "status": "COMPLETED",
                },
                "architect": {
                    "status": "READY",
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
                    "architect": [],
                }
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

    main()

    output = capsys.readouterr().out

    assert "Running agent: architect" in output
    assert (
        "Mock execution completed for agent: architect"
        in output
    )
