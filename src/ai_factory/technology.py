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
