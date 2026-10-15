"""An implementation unit succeeds only if every required phase succeeded.

LinkVault round 4: `npm run prisma:generate` failed, the runtime returned
early with no test results, `all([])` answered True, and the Development Gate
opened on an empty workspace. Success is now fail-closed.
"""

from pathlib import Path

import pytest

from ai_factory.agent_result import (
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.development_gate import evaluate_development_gate
from ai_factory.implementation_batch import run_implementation_batch
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)
from ai_factory.implementation_request import ImplementationTask
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.implementation_runtime import (
    ImplementationExecution,
    run_implementation_task,
)
from ai_factory.setup_runner import SetupExecutionResult
from ai_factory.test_runner import CommandExecutionResult


TASK_ID = "ACME-DEV-UNIT"


def _task(task_id: str = TASK_ID) -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id=task_id,
        title="Unit",
        purpose="Implement it.",
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )


def _setup(command: str, passed: bool) -> SetupExecutionResult:
    return SetupExecutionResult(
        command=command,
        returncode=0 if passed else 1,
        stdout="",
        stderr="" if passed else "failed",
    )


def _test(
    command: str,
    passed: bool,
    stdout: str = "",
) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        returncode=0 if passed else 1,
        stdout=stdout,
        stderr="" if passed else "boom",
    )


def _execution(
    tests: list[str] | None = None,
    setup_commands: list[str] | None = None,
    **kwargs,
) -> ImplementationExecution:
    return ImplementationExecution(
        result=ImplementationResult(
            task_id=TASK_ID,
            summary="Unit.",
            setup_commands=setup_commands or [],
            tests=tests or [],
        ),
        task_id=TASK_ID,
        **kwargs,
    )


# --------------------------------------------------------------------------
# The outcome model
# --------------------------------------------------------------------------


def test_failed_setup_fails_the_unit_when_no_test_ran() -> None:
    execution = _execution(
        setup_commands=["npm run prisma:generate"],
        setup_results=[_setup("npm run prisma:generate", False)],
    )

    assert execution.setup_passed is False
    assert execution.execution_succeeded is False


def test_failed_setup_fails_the_unit_even_with_tests_declared() -> None:
    execution = _execution(
        tests=["npm run typecheck"],
        setup_commands=["npm install --ignore-scripts"],
        setup_results=[_setup("npm install --ignore-scripts", False)],
        test_results=[],
    )

    assert execution.execution_succeeded is False


def test_declared_tests_that_never_ran_fail_the_unit() -> None:
    execution = _execution(
        tests=["npm run typecheck", "npm run build"],
        test_results=[],
    )

    assert execution.tests_executed is False
    assert execution.execution_succeeded is False


def test_passing_setup_alone_is_not_validation_evidence() -> None:
    """Preparing an environment proves nothing about the work.

    This previously succeeded: with no declared test, every phase of the
    outcome model was satisfied by an empty collection. Installing
    dependencies is not evidence that a unit did what it was asked.
    """

    execution = _execution(
        setup_commands=["npm install --ignore-scripts"],
        setup_results=[_setup("npm install --ignore-scripts", True)],
    )

    assert execution.setup_passed is True
    assert execution.validation_evidence_present is False
    assert execution.execution_succeeded is False


def test_a_unit_that_declares_nothing_at_all_does_not_succeed() -> None:
    """A unit that changed nothing and verified nothing proved nothing.

    Also previously a success. Recording it as one would let a Developer
    return empty results for every task and still reach the Development
    Gate with no code and no evidence.
    """

    execution = _execution()

    assert execution.setup_passed is True
    assert execution.tests_executed is True
    assert execution.validations_passed is True

    assert execution.validation_evidence_present is False
    assert execution.execution_succeeded is False


def test_all_tests_passing_succeeds() -> None:
    execution = _execution(
        tests=["npm run typecheck"],
        test_results=[_test("npm run typecheck", True)],
    )

    assert execution.execution_succeeded is True


def test_a_failing_test_fails_the_unit() -> None:
    execution = _execution(
        tests=["npm run typecheck"],
        test_results=[_test("npm run typecheck", False)],
    )

    assert execution.execution_succeeded is False


def test_a_preexisting_failure_is_still_tolerated() -> None:
    """The baseline comparison keeps its current behaviour."""

    execution = _execution(
        tests=["npm run typecheck"],
        baseline_test_results=[
            _test("npm run typecheck", False, stdout="old error")
        ],
        test_results=[
            _test("npm run typecheck", False, stdout="old error")
        ],
    )

    assert execution.execution_succeeded is True


def test_a_new_regression_still_fails() -> None:
    execution = _execution(
        tests=["npm run typecheck"],
        baseline_test_results=[
            _test("npm run typecheck", False, stdout="old error")
        ],
        test_results=[
            _test("npm run typecheck", False, stdout="a different error")
        ],
    )

    assert execution.execution_succeeded is False


def test_a_discarded_transaction_can_never_be_successful() -> None:
    execution = _execution(
        tests=["npm run typecheck"],
        test_results=[_test("npm run typecheck", True)],
        transaction_discarded=True,
    )

    assert execution.execution_succeeded is False


def test_tests_passed_is_an_alias_of_execution_succeeded() -> None:
    execution = _execution(
        setup_commands=["npm run prisma:generate"],
        setup_results=[_setup("npm run prisma:generate", False)],
    )

    assert execution.tests_passed is execution.execution_succeeded


# --------------------------------------------------------------------------
# The exact LinkVault round-4 unit
# --------------------------------------------------------------------------


def _linkvault_result() -> ImplementationResult:
    return ImplementationResult(
        task_id="LV-IMP-001",
        summary="Initialize TypeScript modular-monolith application.",
        files=[
            ImplementationFileChange(
                path=f"src/module{index}.ts",
                content=f"export const module{index} = {index};\n",
            )
            for index in range(17)
        ],
        setup_commands=[
            "npm install --ignore-scripts",
            "npm run prisma:generate",
        ],
        tests=[
            "npm run typecheck",
            "npm run prisma:validate",
            "npm test -- tests/server-app.test.ts",
            "npm run build",
        ],
    )


def test_linkvault_round_4_unit_is_not_successful(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """17 files, npm install PASS, prisma:generate FAIL, no test executed."""

    def setup(**kwargs):
        return _setup(
            kwargs["command"],
            kwargs["command"] != "npm run prisma:generate",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        setup,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: _test(kwargs["command"], True),
    )

    class Provider:
        def implement(self, prompt):
            return _linkvault_result()

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task("LV-IMP-001"),
        context={},
        provider=Provider(),
    )

    assert execution.setup_passed is False
    assert execution.test_results == []
    assert execution.execution_succeeded is False
    assert execution.transaction_discarded is True

    # The workspace is untouched.
    assert not (tmp_path / "src").exists()


def test_linkvault_round_4_batch_and_gate_report_the_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def setup(**kwargs):
        return _setup(
            kwargs["command"],
            kwargs["command"] != "npm run prisma:generate",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        setup,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: _test(kwargs["command"], True),
    )

    class Provider:
        def implement(self, prompt):
            return _linkvault_result()

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=AgentResult(
            status="COMPLETED",
            summary="Planned.",
            implementation_requests=[
                AgentImplementationRequest(
                    id="LV-IMP-001",
                    title="Initialize application",
                    purpose="Initialize it.",
                    kind=ImplementationTaskKind.IMPLEMENTATION,
                    scope=ImplementationScope.TASK,
                    verification=VerificationPolicy(
                        allow_full_suite=False,
                        baseline_required=True,
                    ),
                )
            ],
        ),
        context={},
        provider=Provider(),
    )

    assert batch.test_failed is True
    assert batch.failed_task_id == "LV-IMP-001"
    assert batch.written_files == []

    gate = evaluate_development_gate(
        {
            "last_result": {
                "implementation_blocked": batch.blocked,
                "implementation_test_failed": batch.test_failed,
                "implementation_results": [
                    {"task_id": "LV-IMP-001"}
                ],
                "test_results": [],
            }
        }
    )

    assert gate.ready is False
    assert "tests failed" in gate.reasons[0]


def test_a_blocked_unit_is_still_reported_as_blocked(
    tmp_path: Path,
) -> None:
    """Fail-closed must not turn a blocker into a test failure."""

    class Provider:
        def implement(self, prompt):
            return ImplementationResult(
                task_id=TASK_ID,
                summary="Blocked.",
                tests=["npm run typecheck"],
                blockers=[
                    {
                        "message": "The licence server is unreachable.",
                        "kind": "EXTERNAL_DEPENDENCY",
                        "scope": "EXTERNAL",
                        "fixable_by_agent": False,
                        "requires_human_input": True,
                        "blocking": True,
                    }
                ],
            )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=AgentResult(
            status="COMPLETED",
            summary="Planned.",
            implementation_requests=[
                AgentImplementationRequest(
                    id=TASK_ID,
                    title="Unit",
                    purpose="Implement it.",
                    kind=ImplementationTaskKind.IMPLEMENTATION,
                    scope=ImplementationScope.TASK,
                    verification=VerificationPolicy(
                        allow_full_suite=False,
                        baseline_required=True,
                    ),
                )
            ],
        ),
        context={},
        provider=Provider(),
    )

    assert batch.blocked is True
    assert batch.test_failed is False


def test_a_successful_unit_still_promotes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        lambda **kwargs: _setup(kwargs["command"], True),
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: _test(kwargs["command"], True),
    )

    class Provider:
        def implement(self, prompt):
            return ImplementationResult(
                task_id=TASK_ID,
                summary="Unit.",
                files=[
                    ImplementationFileChange(
                        path="src/app.ts",
                        content="export const app = 1;\n",
                    )
                ],
                setup_commands=["npm install --ignore-scripts"],
                tests=["npm run typecheck"],
            )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=Provider(),
    )

    assert execution.execution_succeeded is True
    assert execution.transaction_discarded is False
    assert (tmp_path / "src" / "app.ts").is_file()
