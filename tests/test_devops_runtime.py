from pathlib import Path

from ai_factory.devops_result import (
    DevOpsResult,
)
from ai_factory.devops_runtime import (
    run_devops_validation,
)


class FakeDevOpsProvider:
    def __init__(
        self,
        result: DevOpsResult,
    ) -> None:
        self.result = result
        self.prompts: list[str] = []

    def validate_devops(
        self,
        prompt: str,
    ) -> DevOpsResult:
        self.prompts.append(
            prompt
        )
        return self.result


def test_run_devops_validation_builds_prompt_and_returns_result(
    tmp_path: Path,
) -> None:
    result = DevOpsResult(
        summary="DevOps validation completed.",
        passed=True,
        deployment_ready=True,
        rollback_strategy=(
            "Redeploy previous stable release."
        ),
    )

    provider = FakeDevOpsProvider(
        result
    )

    execution = run_devops_validation(
        project_root=tmp_path,
        context={
            "project": {
                "name": "Test Project",
            },
            "developer": {
                "implemented_files": [
                    "src/app.py",
                ],
            },
            "security": {
                "security_passed": True,
            },
        },
        provider=provider,
    )

    assert execution.result is result
    assert len(provider.prompts) == 1
    assert execution.prompt == provider.prompts[0]

    assert "# DevOps Validation" in execution.prompt
    assert "src/app.py" in execution.prompt

    assert execution.test_results == []
    assert execution.passed is True


def test_run_devops_validation_executes_declared_tests(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_devops_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_devops_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = DevOpsResult(
        summary="DevOps validation completed.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_devops_sample.py -q",
        ],
        deployment_ready=True,
        rollback_strategy="Rollback.",
    )

    provider = FakeDevOpsProvider(
        result
    )

    execution = run_devops_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert len(execution.test_results) == 1
    assert execution.test_results[0].passed is True
    assert execution.passed is True


def test_devops_execution_fails_when_real_test_fails(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_devops_fail.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_devops_fail():\n"
        "    assert False\n",
        encoding="utf-8",
    )

    result = DevOpsResult(
        summary="DevOps model reported success.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_devops_fail.py -q",
        ],
        deployment_ready=True,
        rollback_strategy="Rollback.",
    )

    provider = FakeDevOpsProvider(
        result
    )

    execution = run_devops_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.result.passed is True
    assert execution.test_results[0].passed is False
    assert execution.passed is False


def test_devops_execution_fails_when_not_deployment_ready(
    tmp_path: Path,
) -> None:
    result = DevOpsResult(
        summary="DevOps validation completed.",
        passed=True,
        deployment_ready=False,
        rollback_strategy="",
    )

    provider = FakeDevOpsProvider(
        result
    )

    execution = run_devops_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.result.passed is True
    assert execution.result.deployment_ready is False
    assert execution.passed is False


def test_devops_execution_fails_when_blocked(
    tmp_path: Path,
) -> None:
    result = DevOpsResult(
        summary="DevOps validation blocked.",
        passed=True,
        blockers=[
            "Deployment credentials unavailable.",
        ],
        deployment_ready=True,
        rollback_strategy="Rollback.",
    )

    provider = FakeDevOpsProvider(
        result
    )

    execution = run_devops_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.passed is False
