import pytest

from ai_factory.implementation_result import (
    ImplementationFileChange,
)
from ai_factory.implementation_validator import (
    validate_implementation_file_change,
    validate_implementation_path,
)


def test_validate_implementation_path_accepts_safe_relative_paths() -> None:
    validate_implementation_path(
        "src/app.py"
    )

    validate_implementation_path(
        "tests/test_app.py"
    )


def test_validate_implementation_path_rejects_empty_path() -> None:
    with pytest.raises(
        ValueError,
        match="path is required",
    ):
        validate_implementation_path(
            "   "
        )


def test_validate_implementation_path_rejects_absolute_path() -> None:
    with pytest.raises(
        ValueError,
        match="Absolute implementation path is not allowed",
    ):
        validate_implementation_path(
            "C:/Users/test/file.py"
        )


def test_validate_implementation_path_rejects_parent_traversal() -> None:
    with pytest.raises(
        ValueError,
        match="Parent path traversal is not allowed",
    ):
        validate_implementation_path(
            "../secret.txt"
        )


def test_validate_implementation_path_rejects_factory_directory() -> None:
    with pytest.raises(
        ValueError,
        match="Protected implementation path is not allowed",
    ):
        validate_implementation_path(
            ".factory/project.yaml"
        )


def test_validate_implementation_path_rejects_git_directory() -> None:
    with pytest.raises(
        ValueError,
        match="Protected implementation path is not allowed",
    ):
        validate_implementation_path(
            ".git/config"
        )


def test_validate_implementation_file_change_accepts_write() -> None:
    change = ImplementationFileChange(
        path="src/app.py",
        content="print('hello')",
    )

    validate_implementation_file_change(
        change
    )


def test_validate_implementation_file_change_rejects_other_operations() -> None:
    change = ImplementationFileChange(
        path="src/app.py",
        content="",
        operation="delete",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported implementation operation",
    ):
        validate_implementation_file_change(
            change
        )
