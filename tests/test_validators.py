from pathlib import Path

from ai_factory.state import save_state
from ai_factory.validators import validate_ux_ui_artifacts


REQUIRED_UX_UI_ARTIFACTS = [
    "knowledge/ux-ui/user-flows.md",
    "knowledge/ux-ui/screen-inventory.md",
    "knowledge/ux-ui/visual-direction.md",
]


def create_project_config(project_root: Path) -> None:
    config_path = project_root / ".factory" / "project.yaml"

    config = {
        "schema_version": 1,
        "project": {
            "name": "Test Project",
            "type": "test",
        },
        "capabilities": {
            "ui": True,
        },
        "design": {
            "enabled": True,
            "groups": {},
        },
        "artifacts": {
            "ux_ui": REQUIRED_UX_UI_ARTIFACTS,
        },
    }

    save_state(config_path, config)


def test_validate_ux_ui_artifacts_returns_empty_when_all_exist(
    tmp_path: Path,
) -> None:
    create_project_config(tmp_path)

    for relative_path in REQUIRED_UX_UI_ARTIFACTS:
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch()

    missing = validate_ux_ui_artifacts(tmp_path)

    assert missing == []


def test_validate_ux_ui_artifacts_returns_missing_files(
    tmp_path: Path,
) -> None:
    create_project_config(tmp_path)

    missing = validate_ux_ui_artifacts(tmp_path)

    assert missing == REQUIRED_UX_UI_ARTIFACTS
