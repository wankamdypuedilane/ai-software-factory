from pathlib import Path

from ai_factory.implementation_result import (
    ImplementationFileChange,
)
from ai_factory.implementation_validator import (
    validate_implementation_file_change,
)


def write_implementation_file(
    project_root: Path,
    change: ImplementationFileChange,
) -> Path:
    """Validate and write one implementation file inside the project."""

    validate_implementation_file_change(
        change
    )

    root = project_root.resolve()

    target = (
        project_root
        / change.path
    ).resolve()

    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"Implementation path escapes project root: {change.path}"
        ) from error

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        change.content,
        encoding="utf-8",
    )

    return target
