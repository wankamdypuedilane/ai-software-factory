from pathlib import Path

import pytest

from ai_factory.generated_file_validation import (
    validate_generated_file,
)


def test_validate_generated_file_accepts_valid_json(
    tmp_path: Path,
) -> None:
    validate_generated_file(
        project_root=tmp_path,
        path="package.json",
        content='{"name":"taskflow"}',
    )


def test_validate_generated_file_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="Generated JSON file is invalid",
    ):
        validate_generated_file(
            project_root=tmp_path,
            path="package.json",
            content='{"name":"taskflow"} trailing',
        )


def test_validate_generated_file_ignores_non_json_files(
    tmp_path: Path,
) -> None:
    validate_generated_file(
        project_root=tmp_path,
        path="src/lib/example.ts",
        content="export const value = 1;",
    )
