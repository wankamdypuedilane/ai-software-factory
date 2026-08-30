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


def test_run_qa_validation_builds_prompt_and_returns_result() -> None:
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

    execution = run_qa_validation(
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


def test_run_qa_validation_preserves_failed_verdict() -> None:
    result = QAResult(
        summary="QA found defects.",
        passed=False,
    )

    provider = FakeQAProvider(
        result
    )

    execution = run_qa_validation(
        context={},
        provider=provider,
    )

    assert execution.result.passed is False
    assert execution.result.summary == (
        "QA found defects."
    )
