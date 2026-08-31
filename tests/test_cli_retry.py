from pathlib import Path

import pytest

from ai_factory.cli import main
from ai_factory.state import load_state, save_state


def test_cli_retry_review_required_agent(
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
                    "status": "REVIEW_REQUIRED",
                }
            }
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "retry",
            "product",
        ],
    )

    main()

    output = capsys.readouterr().out

    assert (
        "Agent 'product' reset to READY for retry."
        in output
    )

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert state["agents"]["product"]["status"] == "READY"
    assert state["project"]["phase"] == "discovery"


def test_cli_retry_rejects_non_retryable_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "agents": {
                "product": {
                    "status": "APPROVED",
                }
            }
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ai-factory",
            "retry",
            "product",
        ],
    )

    with pytest.raises(SystemExit):
        main()

    state = load_state(
        factory_dir / "state.yaml"
    )

    assert state["agents"]["product"]["status"] == "APPROVED"
