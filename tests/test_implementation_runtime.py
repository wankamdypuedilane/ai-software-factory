from pathlib import Path

import pytest

from ai_factory.implementation_request import (
    ImplementationTask,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.implementation_runtime import (
    run_implementation_task,
)


class FakeImplementationProvider:
    def __init__(
        self,
        result: ImplementationResult,
    ) -> None:
        self.result = result
        self.prompt: str | None = None

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompt = prompt
        return self.result


def test_run_implementation_task_executes_and_writes_files(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication with tests.",
    )

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
        tests=[
            "pytest tests/test_auth.py",
        ],
    )

    provider = FakeImplementationProvider(
        result
    )

    implementation_result, written = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
            "human_input": None,
        },
        provider=provider,
    )

    assert implementation_result is result
    assert len(written) == 2

    assert (
        tmp_path / "src" / "accounts" / "models.py"
    ).exists()

    assert (
        tmp_path / "tests" / "test_auth.py"
    ).exists()

    assert provider.prompt is not None
    assert "Task ID: US-001" in provider.prompt


def test_run_implementation_task_rejects_mismatched_task_id(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id="US-999",
            summary="Wrong task.",
        )
    )

    with pytest.raises(
        ValueError,
        match="task ID does not match",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )

    assert not (
        tmp_path / "src"
    ).exists()


def test_run_implementation_task_does_not_write_when_blocked(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication.",
    )

    result = ImplementationResult(
        task_id="US-001",
        summary="Implementation blocked.",
        files=[
            ImplementationFileChange(
                path="src/accounts/models.py",
                content="# models",
            ),
        ],
        blockers=[
            "Authentication requirement is ambiguous.",
        ],
    )

    provider = FakeImplementationProvider(
        result
    )

    implementation_result, written = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert implementation_result.blockers == [
        "Authentication requirement is ambiguous."
    ]

    assert written == []

    assert not (
        tmp_path / "src" / "accounts" / "models.py"
    ).exists()
