from typing import Any


def get_design_gate(state: dict[str, Any]) -> dict[str, Any]:
    """Return the detailed design gate state."""

    design_gate = state.get("design_gate")

    if not isinstance(design_gate, dict):
        raise ValueError(
            "Project state does not contain a valid design_gate."
        )

    return design_gate


def is_design_gate_ready(state: dict[str, Any]) -> bool:
    """Return True when all required designs are ready for human approval."""

    gate = get_design_gate(state)

    passenger_complete = (
        gate["passenger_screens_approved"]
        == gate["passenger_screens_total"]
    )

    driver_complete = (
        gate["driver_screens_approved"]
        == gate["driver_screens_total"]
    )

    return (
        passenger_complete
        and driver_complete
        and not gate["figma_blocked"]
    )
