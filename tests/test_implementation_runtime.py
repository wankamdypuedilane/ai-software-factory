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
        self.prompts: list[str] = []

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompt = prompt
        self.prompts.append(prompt)
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
    )

    provider = FakeImplementationProvider(
        result
    )

    execution = run_implementation_task(
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

    assert execution.result is result
    assert len(execution.written_files) == 2
    assert execution.test_results == []
    assert execution.tests_passed is True

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

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.result.blockers == [
        "Authentication requirement is ambiguous."
    ]

    assert execution.written_files == []
    assert execution.test_results == []
    assert execution.tests_passed is True

    assert not (
        tmp_path / "src" / "accounts" / "models.py"
    ).exists()


def test_run_implementation_task_executes_declared_tests(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_sample():\n"
        "    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="US-010",
        title="Sample test",
        purpose="Validate test execution.",
    )

    result = ImplementationResult(
        task_id="US-010",
        summary="Sample implementation.",
        tests=[
            "python -m pytest tests/test_sample.py -q",
        ],
    )

    provider = FakeImplementationProvider(
        result
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(execution.test_results) == 1
    assert execution.test_results[0].passed is True
    assert execution.tests_passed is True


def test_run_implementation_task_passes_retry_diagnostics_to_prompt(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-002",
        title="Ride creation",
        purpose="Implement ride creation.",
    )

    result = ImplementationResult(
        task_id="US-002",
        summary="Ride creation fixed.",
    )

    provider = FakeImplementationProvider(
        result
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
        retry_test_results=[
            {
                "command": (
                    "python -m pytest "
                    "tests/test_rides.py -q"
                ),
                "returncode": 1,
                "passed": False,
                "stdout": "1 failed",
                "stderr": "AssertionError",
            }
        ],
    )

    assert execution.result is result

    assert len(provider.prompts) == 1

    prompt = provider.prompts[0]

    assert "## Previous Test Failures" in prompt
    assert (
        "python -m pytest tests/test_rides.py -q"
        in prompt
    )
    assert "Return code: 1" in prompt
    assert "1 failed" in prompt
    assert "AssertionError" in prompt
