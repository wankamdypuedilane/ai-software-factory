import json
from pathlib import Path


def validate_generated_file(
    project_root: Path,
    path: str,
    content: str,
) -> None:
    """Validate generated structured files before writing them."""

    suffix = Path(path).suffix.lower()

    if suffix != ".json":
        return

    try:
        json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Generated JSON file is invalid: {path}"
        ) from error
