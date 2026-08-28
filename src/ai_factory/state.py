from pathlib import Path
from typing import Any

import yaml


def load_state(state_path: Path) -> dict[str, Any]:
    """Load a Factory project state from a YAML file."""

    if not state_path.exists():
        raise FileNotFoundError(
            f"Factory state file not found: {state_path}"
        )

    with state_path.open("r", encoding="utf-8") as file:
        state = yaml.safe_load(file)

    if not isinstance(state, dict):
        raise ValueError("Invalid Factory state file.")

    return state


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    """Save a Factory project state to a YAML file."""

    state_path.parent.mkdir(parents=True, exist_ok=True)

    with state_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            state,
            file,
            sort_keys=False,
            allow_unicode=True,
        )

        