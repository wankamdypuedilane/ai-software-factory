from pathlib import Path

from ai_factory.implementation_result import (
    ImplementationFileChange,
)


FORBIDDEN_PATH_PREFIXES = (
    ".factory/",
    ".git/",
)


def validate_implementation_path(
    path: str,
) -> None:
    """Validate a repository-relative implementation path."""

    if not isinstance(path, str) or not path.strip():
        raise ValueError(
            "Implementation file path is required."
        )

    normalized = path.replace("\\", "/")

    candidate = Path(normalized)

    if candidate.is_absolute():
        raise ValueError(
            f"Absolute implementation path is not allowed: {path}"
        )

    if ".." in candidate.parts:
        raise ValueError(
            f"Parent path traversal is not allowed: {path}"
        )

    normalized_lower = normalized.lower()

    if any(
        normalized_lower == prefix.rstrip("/")
        or normalized_lower.startswith(prefix)
        for prefix in FORBIDDEN_PATH_PREFIXES
    ):
        raise ValueError(
            f"Protected implementation path is not allowed: {path}"
        )


def validate_implementation_file_change(
    change: ImplementationFileChange,
) -> None:
    """Validate one implementation file change."""

    validate_implementation_path(
        change.path
    )

    if change.operation != "write":
        raise ValueError(
            f"Unsupported implementation operation: {change.operation}"
        )
