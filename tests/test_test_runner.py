from pathlib import Path

import pytest

from ai_factory.test_runner import (
    run_test_command,
)


def test_run_test_command_executes_allowed_command(
    tmp_path: Path,
) -> None:
    result = run_test_command(
        project_root=tmp_path,
        command="python -m pytest --version",
    )

    assert result.returncode == 0
    assert result.passed is True
    assert result.command == "python -m pytest --version"


def test_run_test_command_rejects_unsafe_command(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="Unsafe shell syntax",
    ):
        run_test_command(
            project_root=tmp_path,
            command="pytest && echo unsafe",
        )
