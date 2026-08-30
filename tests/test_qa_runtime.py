from pathlib import Path

from ai_factory.qa_result import (
    QAResult,
)
from ai_factory.qa_runtime import (
    run_qa_validation,
)


class FakeQAProvider:
    def __init__(
        self,
        result: QAResult,
    ) -> None:
        self.result = result
        self.prompts: list[str] = []

    def validate_qa(
        self,
        prompt: str,
    ) -> QAResult:
        self.prompts.append(
            prompt
        )
        return self.result


def test_run_qa_validation_builds_prompt_and_returns_result(
    tmp_path: Path,
) -> None:
    result = QAResult(
        summary="QA validation completed.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_rides.py -q",
        ],
    )

    provider = FakeQAProvider(
        result
    )

    recorded_commands = []

    def fake_run_test_command(
        project_root,
        command: str,
    ):
        recorded_commands.append(
            (project_root, command)
        )

        return type(
            "FakeCommandExecutionResult",
            (),
            {
                "command": command,
                "returncode": 0,
                "stdout": "ok",
                "stderr": "",
                "passed": True,
            },
        )()

    import ai_factory.qa_runtime as qa_runtime

    original_run_test_command = qa_runtime.run_test_command
    qa_runtime.run_test_command = fake_run_test_command

    try:
        execution = run_qa_validation(
            project_root=tmp_path,
            context={
                "project": {
                    "name": "Test Project",
                },
                "requirements": [
                    "Passenger can request a ride.",
                ],
                "acceptance_criteria": [
                    "Ride request is persisted.",
                ],
                "architecture": {
                    "style": "monolith",
                },
                "developer": {
                    "implemented_files": [
                        "src/rides.py",
                    ],
                    "implementation_results": [
                        {
                            "task_id": "US-001",
                            "summary": "Ride creation implemented.",
                        }
                    ],
                },
            },
            provider=provider,
        )
    finally:
        qa_runtime.run_test_command = original_run_test_command

    assert execution.result is result

    assert len(
        provider.prompts
    ) == 1

    assert execution.prompt == (
        provider.prompts[0]
    )

    assert "# QA Validation" in execution.prompt
    assert "Passenger can request a ride." in execution.prompt
    assert "Ride request is persisted." in execution.prompt
    assert "src/rides.py" in execution.prompt

    assert execution.result.passed is True
    assert len(execution.test_results) == 1
    assert execution.test_results[0].command == (
        "python -m pytest tests/test_rides.py -q"
    )
    assert execution.test_results[0].passed is True
    assert recorded_commands == [
        (
            tmp_path,
            "python -m pytest tests/test_rides.py -q",
        )
    ]


def test_run_qa_validation_preserves_failed_verdict(
    tmp_path: Path,
) -> None:
    result = QAResult(
        summary="QA found defects.",
        passed=False,
    )

    provider = FakeQAProvider(
        result
    )

    import ai_factory.qa_runtime as qa_runtime

    original_run_test_command = qa_runtime.run_test_command
    qa_runtime.run_test_command = lambda *args, **kwargs: None

    try:
        execution = run_qa_validation(
            project_root=tmp_path,
            context={},
            provider=provider,
        )
    finally:
        qa_runtime.run_test_command = original_run_test_command

    assert execution.result.passed is False
    assert execution.result.summary == (
        "QA found defects."
    )
    assert execution.test_results == []


def test_run_qa_validation_executes_declared_tests(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_qa_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_qa_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = QAResult(
        summary="QA validation completed.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_qa_sample.py -q",
        ],
    )

    provider = FakeQAProvider(
        result
    )

    execution = run_qa_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert len(execution.test_results) == 1

    test_result = execution.test_results[0]

    assert (
        test_result.command
        == "python -m pytest tests/test_qa_sample.py -q"
    )
    assert test_result.returncode == 0
    assert test_result.passed is True
