from pathlib import Path

from ai_factory.implementation_result import (
    ImplementationResult,
)
from ai_factory.implementation_validator import (
    validate_implementation_file_change,
)
from ai_factory.implementation_writer import (
    write_implementation_file,
)


def apply_implementation_result(
    project_root: Path,
    result: ImplementationResult,
) -> list[Path]:
    """Validate and apply all file changes from an implementation result."""

    # Validate the complete batch before writing anything.
    for change in result.files:
        validate_implementation_file_change(
            change
        )

    written_files: list[Path] = []

    for change in result.files:
        written_files.append(
            write_implementation_file(
                project_root=project_root,
                change=change,
            )
        )

    return written_files
