from pathlib import Path


UX_UI_REQUIRED_ARTIFACTS = [
    "knowledge/ux-ui/user-flows.md",
    "knowledge/ux-ui/screen-inventory.md",
    "knowledge/ux-ui/visual-direction.md",
    "knowledge/ux-ui/design-system.md",
    "knowledge/ux-ui/high-fidelity-brief.md",
    "knowledge/ux-ui/wireframes/passenger-booking.md",
    "knowledge/ux-ui/wireframes/driver-ride.md",
    "knowledge/ux-ui/wireframes/supporting-screens.md",
    "knowledge/ux-ui/high-fidelity/passenger-screens.md",
    "knowledge/ux-ui/high-fidelity/driver-screens.md",
    "knowledge/ux-ui/high-fidelity/component-specs.md",
]


def validate_ux_ui_artifacts(project_root: Path) -> list[str]:
    """
    Return the list of missing UX/UI artifacts for a project.

    An empty list means the required UX/UI artifact structure exists.
    """

    missing = []

    for relative_path in UX_UI_REQUIRED_ARTIFACTS:
        artifact_path = project_root / relative_path

        if not artifact_path.exists():
            missing.append(relative_path)

    return missing
