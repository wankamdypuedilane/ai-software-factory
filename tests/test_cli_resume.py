from pathlib import Path

import pytest

from ai_factory.cli import main
from ai_factory.state import load_state, save_state


def test_cli_resume_blocked_agent_with_human_input(
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
                "product": {
                    "status": "BLOCKED",
                }
            }
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "inputs": {
                "directory": "knowledge/inputs",
            }
        },
    )

    input_path = (
        tmp_path
        / "knowledge"
        / "inputs"
        / "product.md"
    )

    input_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_path.write_text(
        "The product is a ride-hailing application.",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "resume",
            "product",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert (
        "Agent 'product' resumed and set to READY."
        in output
    )

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert state["agents"]["product"]["status"] == "READY"
    assert state["project"]["phase"] == "discovery"


def test_cli_resume_rejects_missing_human_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "agents": {
                "product": {
                    "status": "BLOCKED",
                }
            }
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "inputs": {
                "directory": "knowledge/inputs",
            }
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "resume",
            "product",
        ],
    )

    with pytest.raises(
        SystemExit,
    ):
        main()

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert state["agents"]["product"]["status"] == "BLOCKED"
