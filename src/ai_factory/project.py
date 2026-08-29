from pathlib import Path

from ai_factory.state import load_state, save_state


def initialize_project(project_name: str, target_dir: Path) -> Path:
    """Initialize a new project using the Factory templates."""

    project_id = project_name.lower().replace(" ", "-")
    project_root = target_dir / project_id
    factory_dir = project_root / ".factory"

    if project_root.exists():
        raise FileExistsError(
            f"Project already exists: {project_root}"
        )

    factory_dir.mkdir(parents=True)

    templates_root = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "project"
    )

    # Initialize workflow state
    state_template_path = templates_root / "state.yaml"
    state = load_state(state_template_path)

    state["project"]["id"] = project_id
    state["project"]["name"] = project_name

    state_path = factory_dir / "state.yaml"
    save_state(state_path, state)

    # Initialize project configuration
    project_template_path = templates_root / "project.yaml"
    project_config = load_state(project_template_path)

    project_config["project"]["name"] = project_name

    project_config_path = factory_dir / "project.yaml"
    save_state(project_config_path, project_config)

    return project_root
