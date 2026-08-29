from typing import Any


VALID_SELECTION_MODES = {
    "recommend",
    "manual",
    "constrained",
}


def get_technology_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    """Return and validate the project's technology configuration."""

    technology = config.get("technology")

    if not isinstance(technology, dict):
        raise ValueError(
            "Project configuration does not contain "
            "a valid technology section."
        )

    return technology


def validate_selection_mode(
    config: dict[str, Any],
) -> str:
    """Validate and return the technology selection mode."""

    technology = get_technology_config(config)

    selection_mode = technology.get("selection_mode")

    if selection_mode not in VALID_SELECTION_MODES:
        raise ValueError(
            f"Invalid technology selection mode: {selection_mode}"
        )

    return selection_mode


def validate_technology_proposal(
    proposal: dict[str, Any],
) -> None:
    """Validate the structure of an Architect technology proposal."""

    if not isinstance(proposal, dict):
        raise ValueError(
            "Technology proposal must be a mapping."
        )

    components = proposal.get("components")

    if not isinstance(components, dict) or not components:
        raise ValueError(
            "Technology proposal must contain components."
        )

    for component_name, component in components.items():
        if not isinstance(component, dict):
            raise ValueError(
                f"Invalid technology component: {component_name}"
            )

        technology = component.get("technology")
        rationale = component.get("rationale")

        if not isinstance(technology, str) or not technology.strip():
            raise ValueError(
                f"Technology is required for component: {component_name}"
            )

        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(
                f"Rationale is required for component: {component_name}"
            )


def validate_proposal_constraints(
    config: dict[str, Any],
    proposal: dict[str, Any],
) -> None:
    """Validate a technology proposal against project constraints."""

    selection_mode = validate_selection_mode(config)

    if selection_mode != "constrained":
        return

    technology_config = get_technology_config(config)
    constraints = technology_config.get("constraints", {})

    if not isinstance(constraints, dict):
        raise ValueError(
            "Technology constraints must be a mapping."
        )

    validate_technology_proposal(proposal)

    components = proposal["components"]

    for component_name, component_constraints in constraints.items():
        if not isinstance(component_constraints, dict):
            raise ValueError(
                f"Invalid constraints for component: {component_name}"
            )

        allowed = component_constraints.get("allowed")

        if allowed is None:
            continue

        if not isinstance(allowed, list):
            raise ValueError(
                f"Allowed technologies for {component_name} "
                "must be a list."
            )

        if component_name not in components:
            raise ValueError(
                f"Required constrained component missing: "
                f"{component_name}"
            )

        proposed_technology = components[
            component_name
        ]["technology"]

        if proposed_technology not in allowed:
            raise ValueError(
                f"Technology '{proposed_technology}' is not allowed "
                f"for component '{component_name}'."
            )


def validate_manual_selection(
    config: dict[str, Any],
    proposal: dict[str, Any],
) -> None:
    """Ensure an Architect proposal respects a manually selected stack."""

    selection_mode = validate_selection_mode(config)

    if selection_mode != "manual":
        return

    technology_config = get_technology_config(config)
    selected = technology_config.get("selected", {})

    if not isinstance(selected, dict):
        raise ValueError(
            "Manually selected technologies must be a mapping."
        )

    validate_technology_proposal(proposal)

    components = proposal["components"]

    for component_name, selected_component in selected.items():
        if not selected_component:
            continue

        if not isinstance(selected_component, dict):
            raise ValueError(
                f"Invalid manual selection for component: "
                f"{component_name}"
            )

        selected_technology = selected_component.get("technology")

        if not isinstance(
            selected_technology,
            str,
        ) or not selected_technology.strip():
            raise ValueError(
                f"Technology is required for manually selected "
                f"component: {component_name}"
            )

        if component_name not in components:
            raise ValueError(
                f"Manually selected component missing from proposal: "
                f"{component_name}"
            )

        proposed_technology = components[
            component_name
        ]["technology"]

        if proposed_technology != selected_technology:
            raise ValueError(
                f"Proposal cannot replace manually selected technology "
                f"'{selected_technology}' for component "
                f"'{component_name}'."
            )


def validate_technology_decision(
    config: dict[str, Any],
    proposal: dict[str, Any],
) -> None:
    """Validate a complete technology decision for the project."""

    selection_mode = validate_selection_mode(config)

    validate_technology_proposal(proposal)

    if selection_mode == "constrained":
        validate_proposal_constraints(
            config,
            proposal,
        )

    elif selection_mode == "manual":
        validate_manual_selection(
            config,
            proposal,
        )
