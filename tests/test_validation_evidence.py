"""A unit that verifies nothing has not succeeded.

`all([])` is True and `len([]) >= len([])` is True, so an implementation
result declaring no verification command at all satisfied every phase of the
outcome model by vacuous truth: setup passed, tests executed, validations
passed. A unit could therefore rewrite governed product files and be promoted
without a single command ever running.

The declared contract decides what evidence is acceptable. It cannot decide
that no evidence is acceptable, because then the model chooses whether it is
verified at all.
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
from ai_factory.validation_evidence import (
    build_missing_validation_correction,
    describe_validation_requirement,
    missing_validation_evidence,
)


SOURCE = ImplementationFileChange(
    path="src/auth/session.ts",
    content="export const session = () => null;\n",
)

TEST_FILE = ImplementationFileChange(
    path="src/auth/session.test.ts",
    content="// covers the session service\n",
)


def _task(
    kind: ImplementationTaskKind = ImplementationTaskKind.IMPLEMENTATION,
    scope: ImplementationScope = ImplementationScope.TASK,
    verification: VerificationPolicy | None = None,
) -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        # Deliberately reassuring prose: the contract decides, not this.
        title="Fully verified session service",
        purpose="Implement the session service with complete test coverage.",
        kind=kind,
        scope=scope,
        verification=verification
        or VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )


class _Provider:
    def __init__(self, *results: ImplementationResult) -> None:
        self.results = list(results)
        self.prompts: list[str] = []

    def implement(self, prompt: str) -> ImplementationResult:
        self.prompts.append(prompt)

        return (
            self.results.pop(0)
            if len(self.results) > 1
            else self.results[0]
        )


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    executed: list[str] = []

    def fake_setup(project_root, command, **_):
        return SetupExecutionResult(
            command=command, returncode=0, stdout="", stderr=""
        )

    def fake_test(project_root, command, **_):
        executed.append(command)

        return CommandExecutionResult(
            command=command, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command", fake_setup
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command", fake_test
    )

    return executed


# --------------------------------------------------------------------------
# The requirement is derived from the contract, never from prose
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "scope"),
    [
        (ImplementationTaskKind.IMPLEMENTATION, ImplementationScope.TASK),
        (ImplementationTaskKind.IMPLEMENTATION, ImplementationScope.PROJECT),
        (
            ImplementationTaskKind.TEST_IMPLEMENTATION,
            ImplementationScope.TASK,
        ),
        (ImplementationTaskKind.VERIFICATION, ImplementationScope.TASK),
        (ImplementationTaskKind.VERIFICATION, ImplementationScope.PROJECT),
    ],
)
def test_no_supported_task_kind_may_declare_zero_validation(
    kind: ImplementationTaskKind,
    scope: ImplementationScope,
) -> None:
    reason = missing_validation_evidence(
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE],
        ),
        kind=kind,
        scope=scope,
    )

    assert reason
    assert describe_validation_requirement(kind, scope).required is True


def test_a_declared_validation_satisfies_the_requirement() -> None:
    assert missing_validation_evidence(
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE, TEST_FILE],
            tests=["npm test -- src/auth/session.test.ts"],
        ),
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
    ) == ""


def test_typecheck_and_build_count_as_evidence() -> None:
    """Existing architecture accepts these; that stays true."""

    assert missing_validation_evidence(
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE],
            tests=["npm run typecheck", "npm run build"],
        ),
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
    ) == ""


def test_a_unit_changing_nothing_and_validating_nothing_is_refused() -> None:
    """Explicit policy for the no-file, no-command case."""

    assert missing_validation_evidence(
        ImplementationResult(task_id="TASK-001", summary="Nothing to do."),
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
    )


def test_reassuring_prose_does_not_satisfy_the_requirement() -> None:
    """No natural-language heuristic anywhere in this rule."""

    result = ImplementationResult(
        task_id="TASK-001",
        summary=(
            "All tests pass. Full coverage. Verified with npm test and "
            "npm run typecheck."
        ),
        files=[SOURCE],
    )

    assert missing_validation_evidence(
        result,
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
    )


def test_the_correction_names_the_task_and_asks_for_a_command() -> None:
    corrections = build_missing_validation_correction(
        task_id="TASK-001",
        result=ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE, TEST_FILE],
        ),
        reason="reason",
    )

    joined = "\n".join(corrections)

    assert "TASK-001" in joined
    assert "src/auth/session.test.ts" in joined
    assert "blocker" in joined


# --------------------------------------------------------------------------
# Runtime enforcement: vacuous truth cannot become success
# --------------------------------------------------------------------------


def test_no_test_results_cannot_become_success_by_vacuous_truth() -> None:
    """Constructed directly, bypassing every producer-side correction."""

    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE],
        ),
        task_id="TASK-001",
    )

    assert execution.setup_passed is True
    assert execution.tests_executed is True

    assert execution.validation_evidence_present is False
    assert execution.execution_succeeded is False
    assert execution.tests_passed is False


def test_setup_only_success_cannot_substitute_for_validation() -> None:
    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE],
            setup_commands=["npm install --ignore-scripts"],
        ),
        task_id="TASK-001",
        setup_results=[
            SetupExecutionResult(
                command="npm install --ignore-scripts",
                returncode=0,
                stdout="",
                stderr="",
            )
        ],
    )

    assert execution.setup_passed is True
    assert execution.execution_succeeded is False


def test_a_discarded_transaction_still_cannot_report_success() -> None:
    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE],
            tests=["npm run typecheck"],
        ),
        task_id="TASK-001",
        test_results=[
            CommandExecutionResult(
                command="npm run typecheck",
                returncode=0,
                stdout="",
                stderr="",
            )
        ],
        transaction_discarded=True,
    )

    assert execution.execution_succeeded is False


def test_a_blocked_unit_fails_without_being_called_a_validation_failure(
) -> None:
    from ai_factory.blocker_contract import (
        Blocker,
        BlockerKind,
        BlockerScope,
    )

    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="TASK-001",
            summary="Blocked.",
            blockers=[
                Blocker(
                    message="Sandbox credentials are unavailable.",
                    kind=BlockerKind.EXTERNAL_DEPENDENCY,
                    scope=BlockerScope.EXTERNAL,
                    fixable_by_agent=False,
                    requires_human_input=True,
                    blocking=True,
                )
            ],
        ),
        task_id="TASK-001",
    )

    assert execution.execution_succeeded is False
    assert execution.validation_evidence_present is False


# --------------------------------------------------------------------------
# Producer-side correction, then fail closed
# --------------------------------------------------------------------------


def test_the_model_is_asked_to_correct_a_zero_validation_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    provider = _Provider(
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE, TEST_FILE],
        ),
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented with verification.",
            files=[SOURCE, TEST_FILE],
            tests=["npm test -- src/auth/session.test.ts"],
        ),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "src/auth/session.test.ts" in provider.prompts[1]
    assert execution.execution_succeeded is True


def test_a_persistent_zero_validation_response_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    provider = _Provider(
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE],
        )
    )

    with pytest.raises(ValueError, match="validation"):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=provider,
        )

    assert not (tmp_path / "src" / "auth" / "session.ts").exists()


def test_a_refused_response_writes_nothing_to_the_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    provider = _Provider(
        ImplementationResult(
            task_id="TASK-001",
            summary="Implemented.",
            files=[SOURCE, TEST_FILE],
        )
    )

    with pytest.raises(ValueError):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=provider,
        )

    assert list(tmp_path.rglob("*.ts")) == []


# --------------------------------------------------------------------------
# Legitimate behaviour preserved
# --------------------------------------------------------------------------


def test_an_implementation_with_a_targeted_test_still_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed = _wire(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=_Provider(
            ImplementationResult(
                task_id="TASK-001",
                summary="Implemented.",
                files=[SOURCE, TEST_FILE],
                tests=["npm test -- src/auth/session.test.ts"],
            )
        ),
    )

    assert execution.execution_succeeded is True
    assert "npm test -- src/auth/session.test.ts" in executed
    assert (tmp_path / "src" / "auth" / "session.ts").is_file()


def test_an_implementation_validated_by_typecheck_and_build_passes(
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
                summary="Implemented.",
                files=[SOURCE],
                tests=["npm run typecheck", "npm run build"],
            )
        ),
    )

    assert execution.execution_succeeded is True


def test_a_project_verification_task_is_unchanged(
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
                summary="Verified.",
                tests=["npm test", "npm run typecheck"],
            )
        ),
    )

    assert execution.execution_succeeded is True


# --------------------------------------------------------------------------
# Batch level: nothing unvalidated reaches the workspace or the gate
# --------------------------------------------------------------------------


def test_an_unvalidated_unit_promotes_nothing_and_holds_the_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    agent_result = AgentResult(
        status="COMPLETED",
        summary="Session service planned.",
        implementation_requests=[
            AgentImplementationRequest(
                id="TASK-001",
                title="Session service",
                purpose="Implement the session service.",
                kind=ImplementationTaskKind.IMPLEMENTATION,
                scope=ImplementationScope.TASK,
                verification=VerificationPolicy(
                    allow_full_suite=False,
                    baseline_required=True,
                ),
            )
        ],
    )

    with pytest.raises(ValueError, match="validation"):
        run_implementation_batch(
            project_root=tmp_path,
            agent_name="developer",
            agent_result=agent_result,
            context={},
            provider=_Provider(
                ImplementationResult(
                    task_id="TASK-001",
                    summary="Implemented.",
                    files=[SOURCE],
                )
            ),
        )

    assert not (tmp_path / "src" / "auth" / "session.ts").exists()

    gate = evaluate_development_gate(
        {
            "status": "FAILED",
            "last_result": {
                "implementation_test_failed": True,
                "implemented_files": [],
            },
        }
    )

    assert gate.ready is False


def test_implemented_files_excludes_unvalidated_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling fail-open reproduction: PASS before, FAIL after."""

    _wire(monkeypatch)

    result = ImplementationResult(
        task_id="TASK-001",
        summary="Implemented.",
        files=[SOURCE],
    )

    # Before: every phase was satisfied by an empty collection.
    legacy = ImplementationExecution(result=result, task_id="TASK-001")

    assert legacy.setup_passed is True
    assert legacy.tests_executed is True
    assert legacy.validations_passed is True

    # After: the unit is refused and contributes nothing.
    assert legacy.execution_succeeded is False
    assert legacy.written_files == []

    with pytest.raises(ValueError):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=_Provider(result),
        )

    assert list(tmp_path.rglob("*.ts")) == []
