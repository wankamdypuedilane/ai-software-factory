from pathlib import Path

from ai_factory.security_result import (
    SecurityResult,
)
from ai_factory.security_runtime import (
    run_security_validation,
)


class FakeSecurityProvider:
    def __init__(
        self,
        result: SecurityResult,
    ) -> None:
        self.result = result
        self.prompts: list[str] = []

    def validate_security(
        self,
        prompt: str,
    ) -> SecurityResult:
        self.prompts.append(
            prompt
        )
        return self.result


def test_run_security_validation_builds_prompt_and_returns_result(
    tmp_path: Path,
) -> None:
    result = SecurityResult(
        summary="Security validation completed.",
        passed=True,
    )

    provider = FakeSecurityProvider(
        result
    )

    execution = run_security_validation(
        project_root=tmp_path,
        context={
            "project": {
                "name": "Test Project",
            },
            "developer": {
                "implemented_files": [
                    "src/auth.py",
                ],
            },
            "qa": {
                "qa_passed": True,
            },
        },
        provider=provider,
    )

    assert execution.result is result

    assert len(provider.prompts) == 1

    assert execution.prompt == (
        provider.prompts[0]
    )

    assert "# Security Validation" in execution.prompt
    assert "src/auth.py" in execution.prompt

    assert execution.test_results == []
    assert execution.passed is True


def test_run_security_validation_executes_declared_tests(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_security_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_security_sample():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = SecurityResult(
        summary="Security validation completed.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_security_sample.py -q",
        ],
    )

    provider = FakeSecurityProvider(
        result
    )

    execution = run_security_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert len(execution.test_results) == 1
    assert execution.test_results[0].passed is True
    assert execution.passed is True


def test_security_execution_fails_when_real_test_fails(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_security_fail.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_security_fail():\n"
        "    assert False\n",
        encoding="utf-8",
    )

    result = SecurityResult(
        summary="Security model reported success.",
        passed=True,
        test_commands=[
            "python -m pytest tests/test_security_fail.py -q",
        ],
    )

    provider = FakeSecurityProvider(
        result
    )

    execution = run_security_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.result.passed is True
    assert execution.test_results[0].passed is False
    assert execution.passed is False


def test_security_execution_fails_when_blocked(
    tmp_path: Path,
) -> None:
    result = SecurityResult(
        summary="Security validation blocked.",
        passed=True,
        blockers=[
            "Security test environment unavailable.",
        ],
    )

    provider = FakeSecurityProvider(
        result
    )

    execution = run_security_validation(
        project_root=tmp_path,
        context={},
        provider=provider,
    )

    assert execution.passed is False
