from typing import Any


def apply_approved_technology_to_config(
    config: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Copy the approved Technology Gate proposal into project config."""

    technology = config.get("technology")

    if not isinstance(technology, dict):
        raise ValueError(
            "Project configuration does not contain valid technology settings."
        )

    gate = state.get("technology_gate")

    if not isinstance(gate, dict):
        raise ValueError(
            "Project state does not contain a valid technology_gate."
        )

    if gate.get("status") != "APPROVED":
        raise ValueError(
            "Technology Gate must be approved before applying technology."
        )

    if gate.get("human_approval") is not True:
        raise ValueError(
            "Technology Gate requires human approval."
        )

    proposal = gate.get("proposal")

    if not isinstance(proposal, dict) or not proposal:
        raise ValueError(
            "Technology Gate does not contain a valid proposal."
        )

    components = proposal.get("components")

    if not isinstance(components, dict):
        raise ValueError(
            "Technology proposal does not contain valid components."
        )

    selected = technology.get("selected")

    if not isinstance(selected, dict):
        raise ValueError(
            "Project technology.selected must be a mapping."
        )

    for component_name, component_data in components.items():
        if not isinstance(component_data, dict):
            raise ValueError(
                f"Invalid technology component: {component_name}"
            )

        technology_name = component_data.get(
            "technology"
        )

        if not isinstance(technology_name, str) or not technology_name.strip():
            raise ValueError(
                f"Technology is required for component '{component_name}'."
            )

        selected[component_name] = {
            "technology": technology_name,
            "rationale": component_data.get(
                "rationale",
                "",
            ),
        }

    return config
