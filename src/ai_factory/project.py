from pathlib import Path

from ai_factory.state import load_state, save_state


def initialize_project(project_name: str, target_dir: Path) -> Path:
    """Initialize a new project using the Factory template."""

    project_id = project_name.lower().replace(" ", "-")
    project_root = target_dir / project_id
    factory_dir = project_root / ".factory"

    if project_root.exists():
        raise FileExistsError(
            f"Project already exists: {project_root}"
        )

    factory_dir.mkdir(parents=True)

    template_path = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "project"
        / "state.yaml"
    )

    state = load_state(template_path)

    state["project"]["id"] = project_id
    state["project"]["name"] = project_name

    state_path = factory_dir / "state.yaml"

    save_state(state_path, state)

    return project_root