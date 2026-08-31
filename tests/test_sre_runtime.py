from pathlib import Path

from ai_factory.sre_result import (
    SREResult,
)
from ai_factory.sre_runtime import (
    run_sre_validation,
)


class FakeSREProvider:
    def __init__(
        self,
        result: SREResult,
    ) -> None:
        self.result = result
        self.prompts: list[str] = []

    def validate_sre(
        self,
        prompt: str,
    ) -> SREResult:
        self.prompts.append(
            prompt
        )
        return self.result


def test_run_sre_validation_builds_prompt_and_returns_result(
    tmp_path: Path,
) -> None:
    result = SREResult(
        summary="SRE validation completed.",
        passed=True,
        observability_ready=True,
        incident_readiness=True,
    )

    provider = FakeSREProvider(
        result
    )

    execution = run_sre_validation(
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
            "devops": {
                "deployment_ready": True,
            },
        },
        provider=provider,
    )

    assert execution.result is result
    assert len(provider.prompts) == 1
    assert execution.prompt == provider.prompts[0]

    assert "# SRE Validation" in execution.prompt
    assert "src/app.py" in execution.prompt

    assert execution.test_results == []
    assert execution.passed is True


def test_run_sre_validation_executes_declared_tests(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_sre_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_sre_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = SREResult(
        summary="SRE validation completed.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_sre_sample.py -q",
        ],
        observability_ready=True,
        incident_readiness=True,
    )

    provider = FakeSREProvider(
        result
    )

    execution = run_sre_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert len(execution.test_results) == 1
    assert execution.test_results[0].passed is True
    assert execution.passed is True


def test_sre_execution_fails_when_real_test_fails(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_sre_fail.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_sre_fail():\n"
        "    assert False\n",
        encoding="utf-8",
    )

    result = SREResult(
        summary="SRE model reported success.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_sre_fail.py -q",
        ],
        observability_ready=True,
        incident_readiness=True,
    )

    provider = FakeSREProvider(
        result
    )

    execution = run_sre_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.result.passed is True
    assert execution.test_results[0].passed is False
    assert execution.passed is False


def test_sre_execution_fails_when_observability_not_ready(
    tmp_path: Path,
) -> None:
    result = SREResult(
        summary="Observability is incomplete.",
        passed=True,
        observability_ready=False,
        incident_readiness=True,
    )

    provider = FakeSREProvider(
        result
    )

    execution = run_sre_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.result.passed is True
    assert execution.result.observability_ready is False
    assert execution.passed is False


def test_sre_execution_fails_when_incident_readiness_missing(
    tmp_path: Path,
) -> None:
    result = SREResult(
        summary="Incident readiness is incomplete.",
        passed=True,
        observability_ready=True,
        incident_readiness=False,
    )

    provider = FakeSREProvider(
        result
    )

    execution = run_sre_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.passed is False


def test_sre_execution_fails_when_blocked(
    tmp_path: Path,
) -> None:
    result = SREResult(
        summary="SRE validation blocked.",
        passed=True,
        blockers=[
            "Telemetry environment unavailable.",
        ],
        observability_ready=True,
        incident_readiness=True,
    )

    provider = FakeSREProvider(
        result
    )

    execution = run_sre_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.passed is False
