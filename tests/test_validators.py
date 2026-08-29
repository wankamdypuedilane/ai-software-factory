from pathlib import Path

from ai_factory.validators import validate_ux_ui_artifacts


def test_validate_ux_ui_artifacts_returns_empty_when_all_exist(
    tmp_path: Path,
) -> None:
    required_files = [
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

    for relative_path in required_files:
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch()

    missing = validate_ux_ui_artifacts(tmp_path)

    assert missing == []


def test_validate_ux_ui_artifacts_returns_missing_files(
    tmp_path: Path,
) -> None:
    missing = validate_ux_ui_artifacts(tmp_path)

    assert "knowledge/ux-ui/user-flows.md" in missing
    assert "knowledge/ux-ui/design-system.md" in missing
    assert "knowledge/ux-ui/high-fidelity/component-specs.md" in missing
