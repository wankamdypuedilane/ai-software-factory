import re
import unicodedata
from pathlib import Path
from typing import Any

from ai_factory.resources import get_templates_dir
from ai_factory.state import load_state, save_state


def project_slug(project_name: str) -> str:
    """Return a folder-safe project id: ASCII letters, digits and dashes.

    Accents are folded ("Réservations" -> "reservations") so the id stays
    usable in a URL and on every file system.
    """

    folded = (
        unicodedata.normalize("NFKD", project_name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )

    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")

    if not slug:
        raise ValueError(
            "Project name must contain letters or digits."
        )

    return slug


def initialize_project(project_name: str, target_dir: Path) -> Path:
    """Initialize a new project using the Factory templates."""

    project_id = project_slug(project_name)
    project_root = target_dir / project_id
    factory_dir = project_root / ".factory"

    if project_root.exists():
        raise FileExistsError(
            f"Project already exists: {project_root}"
        )

    factory_dir.mkdir(parents=True)

    templates_root = get_templates_dir() / "project"

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

    # Initialize the human input the Product agent starts from
    product_input_path = get_product_input_path(
        project_root,
        project_config,
    )
    product_input_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    product_input_path.write_text(
        (templates_root / "inputs" / "product.md").read_text(
            encoding="utf-8",
        ),
        encoding="utf-8",
    )

    return project_root


def get_product_input_path(
    project_root: Path,
    project_config: dict[str, Any],
) -> Path:
    """Return the path of the Product agent input file."""

    inputs_config = project_config.get("inputs", {})

    input_directory = "knowledge/inputs"

    if isinstance(inputs_config, dict):
        input_directory = inputs_config.get(
            "directory",
            input_directory,
        )

    return project_root / input_directory / "product.md"
