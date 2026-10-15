"""A validation that never had a target is not a validation.

Round 13 promoted an implementation unit whose own declared verification was
`npm test -- src/auth/routes.test.ts` while that file existed neither before
nor after the unit ran. Both executions printed the same "no test files"
message, the baseline-equivalence rule read the two identical failures as a
pre-existing condition the unit had not worsened, and `src/auth/routes.ts`
and `src/auth/session.ts` were promoted with `execution_succeeded=True`.

Baseline tolerance exists for a real failing test the unit did not worsen. It
must not cover a validation that had nothing to execute. The engine therefore
establishes structurally - from the command grammar it already publishes and
from the transaction filesystem - that a targeted command had a target at all.
"""

from pathlib import Path

import pytest

from ai_factory.agent_result import (
    AgentImplementationRequest,
    AgentResult,
)
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
from ai_factory.implementation_runtime import run_implementation_task
from ai_factory.setup_runner import SetupExecutionResult
from ai_factory.test_runner import CommandExecutionResult
from ai_factory.validation_target import (
    extract_validation_targets,
    find_invalid_validation_targets,
    is_targeted_validation,
)


NO_TEST_FILES = (
    "filter:  src/auth/routes.test.ts\n"
    "include: src/**/*.test.ts\n"
    "\n"
    "No test files found, exiting with code 1\n"
)


# --------------------------------------------------------------------------
# Deterministic target extraction, from the published grammar
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("npm test -- src/auth/routes.test.ts",
         ["src/auth/routes.test.ts"]),
        ("npm run test -- src/auth/routes.test.ts",
         ["src/auth/routes.test.ts"]),
        ("npm test -- src/a.test.ts src/b.test.ts",
         ["src/a.test.ts", "src/b.test.ts"]),
        ("npm test -- --run src/a.test.ts", ["src/a.test.ts"]),
        ("pytest tests/test_auth.py", ["tests/test_auth.py"]),
        ("python -m pytest tests/test_auth.py", ["tests/test_auth.py"]),
        ("pytest tests/test_auth.py::test_login",
         ["tests/test_auth.py"]),
        ("pytest -q tests/test_auth.py", ["tests/test_auth.py"]),
        ("pytest tests/", ["tests/"]),
    ],
)
def test_supported_targeted_commands_expose_their_target(
    command: str,
    expected: list[str],
) -> None:
    assert extract_validation_targets(command) == expected
    assert is_targeted_validation(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "npm test",
        "npm run test",
        "npm run typecheck",
        "npm run build",
        "npm run lint",
        "npm run prisma:validate",
        "pytest",
        "python -m pytest",
    ],
)
def test_full_suite_commands_declare_no_target(command: str) -> None:
    """Non-targeted verification semantics stay exactly as they were."""

    assert extract_validation_targets(command) == []
    assert is_targeted_validation(command) is False


def test_a_non_path_filter_is_not_treated_as_a_target() -> None:
    """Conservative: an unrecognised token never invents a failure."""

    assert extract_validation_targets("npm test -- password") == []


def test_target_detection_needs_no_framework_prose(tmp_path: Path) -> None:
    """Nothing here reads Vitest, Jest or pytest output."""

    (tmp_path / "src").mkdir()

    invalid = find_invalid_validation_targets(
        commands=["npm test -- src/auth/routes.test.ts"],
        root=tmp_path,
    )

    assert invalid == ["src/auth/routes.test.ts"]

    (tmp_path / "src" / "auth").mkdir()
    (tmp_path / "src" / "auth" / "routes.test.ts").write_text(
        "// test", encoding="utf-8"
    )

    assert find_invalid_validation_targets(
        commands=["npm test -- src/auth/routes.test.ts"],
        root=tmp_path,
    ) == []


def test_a_directory_target_is_valid(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()

    assert find_invalid_validation_targets(
        commands=["pytest tests/"],
        root=tmp_path,
    ) == []


# --------------------------------------------------------------------------
# Execution semantics
# --------------------------------------------------------------------------


def _task(
    task_id: str = "TASK-001",
    kind: ImplementationTaskKind = ImplementationTaskKind.IMPLEMENTATION,
    scope: ImplementationScope = ImplementationScope.TASK,
    verification: VerificationPolicy | None = None,
) -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id=task_id,
        title="Authentication routes",
        purpose="Expose the authentication routes.",
        kind=kind,
        scope=scope,
        verification=verification
        or VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )


class _Provider:
    def __init__(self, result: ImplementationResult) -> None:
        self.result = result

    def implement(self, prompt: str) -> ImplementationResult:
        return self.result


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: dict[str, bool] | None = None,
    stderr: str = NO_TEST_FILES,
) -> list[str]:
    """Run declared commands with a deterministic, prose-identical result."""

    executed: list[str] = []
    outcomes = outcomes or {}

    def fake_setup(project_root, command, **_):
        return SetupExecutionResult(
            command=command, returncode=0, stdout="", stderr=""
        )

    def fake_test(project_root, command, **_):
        executed.append(command)

        # A real runner cannot execute a target that is not there, and says
        # so differently from a genuine assertion failure. The baseline runs
        # before the unit is applied, so a test the unit authors is missing
        # then and present afterwards.
        missing = [
            target
            for target in extract_validation_targets(command)
            if not (Path(project_root) / target).exists()
        ]

        if missing:
            return CommandExecutionResult(
                command=command,
                returncode=1,
                stdout="",
                stderr=NO_TEST_FILES,
            )

        passed = outcomes.get(command, True)

        return CommandExecutionResult(
            command=command,
            returncode=0 if passed else 1,
            stdout="",
            stderr="" if passed else stderr,
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        fake_setup,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_test,
    )

    return executed


def test_a_target_absent_before_and_after_fails_the_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Round-13 reproduction, exactly."""

    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                    ImplementationFileChange(
                        path="src/auth/session.ts",
                        content="export const session = () => null;\n",
                    ),
                ],
                tests=[
                    "npm test -- src/auth/routes.test.ts",
                    "npm run typecheck",
                ],
            )
        ),
    )

    assert execution.execution_succeeded is False
    assert execution.transaction_discarded is True
    assert execution.invalid_validation_targets == [
        "src/auth/routes.test.ts"
    ]

    assert not (tmp_path / "src" / "auth" / "routes.ts").exists()
    assert not (tmp_path / "src" / "auth" / "session.ts").exists()


def test_identical_baseline_and_final_output_cannot_rescue_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Byte-identical failures are exactly what used to make this pass."""

    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    baseline = {
        result.command: (result.stdout, result.stderr)
        for result in execution.baseline_test_results
    }
    final = {
        result.command: (result.stdout, result.stderr)
        for result in execution.test_results
    }

    command = "npm test -- src/auth/routes.test.ts"

    assert baseline[command] == final[command]
    assert execution.validations_passed is False
    assert execution.execution_succeeded is False


def test_a_unit_that_authors_its_targeted_test_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent before, present after because the unit wrote it."""

    _wire(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                    ImplementationFileChange(
                        path="src/auth/routes.test.ts",
                        content="// covers the routes\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert execution.invalid_validation_targets == []
    assert execution.execution_succeeded is True
    assert (tmp_path / "src" / "auth" / "routes.test.ts").is_file()


def test_an_existing_target_present_before_and_after_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "routes.test.ts").write_text(
        "// existing test\n", encoding="utf-8"
    )

    _wire(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert execution.invalid_validation_targets == []
    assert execution.execution_succeeded is True


def test_a_genuine_pre_existing_failure_is_still_tolerated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline comparison must stay useful for a real failing test."""

    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "routes.test.ts").write_text(
        "// an existing, already failing test\n", encoding="utf-8"
    )

    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
        stderr="AssertionError: expected 1 to equal 2\n",
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Unrelated change.",
                files=[
                    ImplementationFileChange(
                        path="src/unrelated/helper.ts",
                        content="export const helper = () => null;\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert execution.invalid_validation_targets == []
    assert execution.validations_passed is True
    assert execution.execution_succeeded is True


def test_an_authored_target_whose_test_fails_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
        stderr="AssertionError: routes are not registered\n",
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                    ImplementationFileChange(
                        path="src/auth/routes.test.ts",
                        content="// covers the routes\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert execution.invalid_validation_targets == []
    assert execution.execution_succeeded is False
    assert execution.transaction_discarded is True
    assert not (tmp_path / "src" / "auth" / "routes.ts").exists()


def test_a_successful_targeted_validation_proves_its_target_existed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.test.ts",
                        content="// covers the routes\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert execution.execution_succeeded is True

    for command in execution.result.tests:
        for target in extract_validation_targets(command):
            assert (tmp_path / target).exists()


def test_a_discarded_transaction_is_never_successful(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert execution.transaction_discarded is True
    assert execution.execution_succeeded is False
    assert execution.tests_passed is False


def test_full_suite_verification_semantics_are_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(
            kind=ImplementationTaskKind.VERIFICATION,
            scope=ImplementationScope.PROJECT,
            verification=VerificationPolicy(
                allow_full_suite=True,
                baseline_required=False,
            ),
        ),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Full verification.",
                tests=["npm test", "npm run typecheck"],
            )
        ),
    )

    assert execution.invalid_validation_targets == []
    assert execution.execution_succeeded is True


# --------------------------------------------------------------------------
# Batch level: nothing invalid may reach the workspace or the gate
# --------------------------------------------------------------------------


def _agent_result(tests: list[str], files: list[tuple[str, str]]):
    return AgentResult(
        status="COMPLETED",
        summary="Authentication planned.",
        implementation_requests=[
            AgentImplementationRequest(
                id="TASK-001",
                title="Authentication routes",
                purpose="Expose the authentication routes.",
                kind=ImplementationTaskKind.IMPLEMENTATION,
                scope=ImplementationScope.TASK,
                verification=VerificationPolicy(
                    allow_full_suite=False,
                    baseline_required=True,
                ),
            )
        ],
    )


def test_an_invalid_targeted_validation_promotes_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch level: the Round-13 unit contributes nothing."""

    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
    )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=_agent_result([], []),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                    ImplementationFileChange(
                        path="src/auth/session.ts",
                        content="export const session = () => null;\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    assert batch.test_failed is True
    assert batch.failed_task_id == "TASK-001"
    assert batch.written_files == []

    assert not (tmp_path / "src" / "auth" / "routes.ts").exists()
    assert not (tmp_path / "src" / "auth" / "session.ts").exists()


def test_an_invalid_targeted_validation_keeps_the_gate_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_factory.development_gate import evaluate_development_gate

    _wire(
        monkeypatch,
        outcomes={"npm test -- src/auth/routes.test.ts": False},
    )

    batch = run_implementation_batch(
        project_root=tmp_path,
        agent_name="developer",
        agent_result=_agent_result([], []),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Authentication routes implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/auth/routes.ts",
                        content="export const routes = () => null;\n",
                    ),
                ],
                tests=["npm test -- src/auth/routes.test.ts"],
            )
        ),
    )

    developer_state = {
        "status": "FAILED",
        "last_result": {
            "implementation_test_failed": batch.test_failed,
            "implemented_files": [
                str(path) for path in batch.written_files
            ],
        },
    }

    gate = evaluate_development_gate(developer_state)

    assert gate.ready is False
    assert gate.reasons
