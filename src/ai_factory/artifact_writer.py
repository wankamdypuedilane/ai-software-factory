from pathlib import Path


def write_artifact(
    project_root: Path,
    artifact_path: str,
    content: str,
) -> Path:
    """Write generated artifact content inside the project root."""

    if not artifact_path.strip():
        raise ValueError(
            "Artifact path cannot be empty."
        )

    root = project_root.resolve()
    target = (
        project_root
        / artifact_path
    ).resolve()

    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Artifact path must remain inside the project root."
        ) from error

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        content,
        encoding="utf-8",
    )

    return target
