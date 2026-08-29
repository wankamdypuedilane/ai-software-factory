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
