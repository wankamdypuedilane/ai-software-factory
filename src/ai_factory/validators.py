from pathlib import Path

from ai_factory.state import load_state


def validate_ux_ui_artifacts(project_root: Path) -> list[str]:
    """
    Return the list of missing UX/UI artifacts for a project.

    Required artifacts are defined by the project's own configuration:
    .factory/project.yaml

    An empty list means the required UX/UI artifact structure exists.
    """

    config_path = project_root / ".factory" / "project.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Project configuration not found: {config_path}"
        )

    config = load_state(config_path)

    artifacts = config.get("artifacts", {})
    required_artifacts = artifacts.get("ux_ui", [])

    if not isinstance(required_artifacts, list):
        raise ValueError(
            "Project UX/UI artifacts configuration must be a list."
        )

    missing = []

    for relative_path in required_artifacts:
        artifact_path = project_root / relative_path

        if not artifact_path.exists():
            missing.append(relative_path)

    return missing
