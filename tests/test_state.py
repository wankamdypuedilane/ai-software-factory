from pathlib import Path

import pytest

from ai_factory.state import load_state, save_state


def test_save_and_load_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    expected_state = {
        "factory_version": "1.0",
        "project": {
            "id": "rideflow",
            "name": "RideFlow",
            "phase": "discovery",
        },
    }

    save_state(state_path, expected_state)

    loaded_state = load_state(state_path)

    assert loaded_state == expected_state


def test_load_missing_state_raises_error(tmp_path: Path) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    with pytest.raises(FileNotFoundError):
        load_state(state_path)

        