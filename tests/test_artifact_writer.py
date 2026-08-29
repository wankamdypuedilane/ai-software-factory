from pathlib import Path

import pytest

from ai_factory.artifact_writer import write_artifact


def test_write_artifact_creates_file_inside_project(
    tmp_path: Path,
) -> None:
    target = write_artifact(
        project_root=tmp_path,
        artifact_path="knowledge/project/vision.md",
        content="# Product Vision",
    )

    assert target.exists()
    assert target.read_text(
        encoding="utf-8",
    ) == "# Product Vision"


def test_write_artifact_creates_parent_directories(
    tmp_path: Path,
) -> None:
    target = write_artifact(
        project_root=tmp_path,
        artifact_path="knowledge/product/requirements.md",
        content="# Requirements",
    )

    assert target.parent.exists()
    assert target.name == "requirements.md"


def test_write_artifact_rejects_path_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="inside the project root",
    ):
        write_artifact(
            project_root=tmp_path,
            artifact_path="../outside.md",
            content="Unsafe content",
        )


def test_write_artifact_rejects_empty_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        write_artifact(
            project_root=tmp_path,
            artifact_path="   ",
            content="Content",
        )
