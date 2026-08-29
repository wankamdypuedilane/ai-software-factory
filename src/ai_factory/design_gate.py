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
    """Return True when all configured design groups are complete."""

    gate = get_design_gate(state)

    groups = gate.get("groups", {})

    if not isinstance(groups, dict):
        raise ValueError(
            "Design gate groups must be a mapping."
        )

    external_blockers = gate.get("external_blockers", [])

    if not isinstance(external_blockers, list):
        raise ValueError(
            "Design gate external_blockers must be a list."
        )

    for group_name, group_data in groups.items():
        if not isinstance(group_data, dict):
            raise ValueError(
                f"Invalid design group: {group_name}"
            )

        approved = group_data.get("approved", 0)
        total = group_data.get("total", 0)

        if approved != total:
            return False

    return len(external_blockers) == 0
