from pathlib import Path

import pytest

from ai_factory.implementation_result import (
    ImplementationFileChange,
)
from ai_factory.implementation_writer import (
    write_implementation_file,
)


def test_write_implementation_file_creates_file(
    tmp_path: Path,
) -> None:
    change = ImplementationFileChange(
        path="src/app.py",
        content="print('hello')",
    )

    target = write_implementation_file(
        project_root=tmp_path,
        change=change,
    )

    assert target.exists()
    assert target == (
        tmp_path
        / "src"
        / "app.py"
    )

    assert target.read_text(
        encoding="utf-8",
    ) == "print('hello')"


def test_write_implementation_file_creates_parent_directories(
    tmp_path: Path,
) -> None:
    change = ImplementationFileChange(
        path="src/accounts/models.py",
        content="# models",
    )

    target = write_implementation_file(
        project_root=tmp_path,
        change=change,
    )

    assert target.parent.exists()
    assert target.name == "models.py"


def test_write_implementation_file_rejects_protected_path(
    tmp_path: Path,
) -> None:
    change = ImplementationFileChange(
        path=".factory/state.yaml",
        content="unsafe",
    )

    with pytest.raises(
        ValueError,
        match="Protected implementation path is not allowed",
    ):
        write_implementation_file(
            project_root=tmp_path,
            change=change,
        )


def test_write_implementation_file_rejects_parent_traversal(
    tmp_path: Path,
) -> None:
    change = ImplementationFileChange(
        path="../outside.py",
        content="unsafe",
    )

    with pytest.raises(
        ValueError,
        match="Parent path traversal is not allowed",
    ):
        write_implementation_file(
            project_root=tmp_path,
            change=change,
        )
