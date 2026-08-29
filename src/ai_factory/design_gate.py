from typing import Any


def get_design_gate(state: dict[str, Any]) -> dict[str, Any]:
    """Return the detailed design gate state."""

    design_gate = state.get("design_gate")

    if not isinstance(design_gate, dict):
        raise ValueError(
            "Project state does not contain a valid design_gate."
        )

    return design_gate
