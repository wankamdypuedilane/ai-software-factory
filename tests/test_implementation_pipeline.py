from pathlib import Path

import pytest

from ai_factory.implementation_pipeline import (
    apply_implementation_result,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)


def test_apply_implementation_result_writes_all_files(
    tmp_path: Path,
) -> None:
    result = ImplementationResult(
        task_id="US-001",
        summary="Authentication implemented.",
        files=[
            ImplementationFileChange(
                path="src/accounts/models.py",
                content="# models",
            ),
            ImplementationFileChange(
                path="tests/test_auth.py",
                content="# tests",
            ),
        ],
    )

    written = apply_implementation_result(
        project_root=tmp_path,
        result=result,
    )

    assert len(written) == 2

    assert (
        tmp_path / "src" / "accounts" / "models.py"
    ).read_text(
        encoding="utf-8",
    ) == "# models"

    assert (
        tmp_path / "tests" / "test_auth.py"
    ).read_text(
        encoding="utf-8",
    ) == "# tests"


def test_apply_implementation_result_validates_entire_batch_before_writing(
    tmp_path: Path,
) -> None:
    safe_path = (
        tmp_path
        / "src"
        / "app.py"
    )

    result = ImplementationResult(
        task_id="US-002",
        summary="Unsafe implementation.",
        files=[
            ImplementationFileChange(
                path="src/app.py",
                content="print('safe')",
            ),
            ImplementationFileChange(
                path=".factory/state.yaml",
                content="unsafe",
            ),
        ],
    )

    with pytest.raises(
        ValueError,
        match="Protected implementation path is not allowed",
    ):
        apply_implementation_result(
            project_root=tmp_path,
            result=result,
        )

    assert not safe_path.exists()


def test_apply_implementation_result_returns_empty_list_without_files(
    tmp_path: Path,
) -> None:
    result = ImplementationResult(
        task_id="US-003",
        summary="No changes required.",
    )

    written = apply_implementation_result(
        project_root=tmp_path,
        result=result,
    )

    assert written == []
