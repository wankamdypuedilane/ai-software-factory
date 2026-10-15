"""QA cannot pass itself.

`QAExecution.passed` was `result.passed and all(test_results) and not
blockers`. With no executed check, `all([])` is True and the whole decision
collapsed to `result.passed` - the QA agent's own claim about its own work.
The QA Gate then read `qa_passed`, became READY_FOR_REVIEW, and the only
thing standing between "I passed" and Security was a human reading a summary.

The agent may propose a test plan, commands, defects and findings. Whether QA
passed is decided by what the engine executed.
"""

from pathlib import Path

import pytest

from ai_factory.approval_runtime import apply_approval
from ai_factory.blocker_contract import (
    Blocker,
    BlockerKind,
    BlockerScope,
)
from ai_factory.qa_evidence import (
    BLOCKING_DEFECT_SEVERITIES,
    QAEvidence,
    describe_qa_evidence,
    missing_qa_evidence,
    qa_evidence_satisfied,
)
from ai_factory.qa_gate import evaluate_qa_gate
from ai_factory.qa_gate_runtime import update_qa_gate_from_state
from ai_factory.qa_result import QADefect, QAResult
from ai_factory.qa_runtime import QAExecution, run_qa_validation
from ai_factory.test_runner import CommandExecutionResult


def _check(command: str, passed: bool = True) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        returncode=0 if passed else 1,
        stdout="",
        stderr="" if passed else "AssertionError",
    )


def _serialized(command: str, passed: bool = True) -> dict:
    return {
        "command": command,
        "returncode": 0 if passed else 1,
        "passed": passed,
        "stdout": "",
        "stderr": "" if passed else "AssertionError",
    }


def _defect(severity: str) -> QADefect:
    return QADefect(
        id="QA-001",
        title="Checkout total is wrong",
        severity=severity,
        related_story="US-010",
        expected="42",
        actual="41",
    )


def _external_blocker() -> Blocker:
    return Blocker(
        message="The staging environment is unavailable.",
        kind=BlockerKind.EXTERNAL_DEPENDENCY,
        scope=BlockerScope.EXTERNAL,
        fixable_by_agent=False,
        requires_human_input=True,
        blocking=True,
    )


def _execution(
    passed: bool = True,
    test_commands: list[str] | None = None,
    test_results: list[CommandExecutionResult] | None = None,
    defects: list[QADefect] | None = None,
    blockers: list[Blocker] | None = None,
    summary: str = "QA validation completed.",
) -> QAExecution:
    return QAExecution(
        result=QAResult(
            summary=summary,
            passed=passed,
            defects=defects or [],
            test_commands=test_commands or [],
            blockers=blockers or [],
        ),
        prompt="prompt",
        test_results=test_results or [],
    )


# --------------------------------------------------------------------------
# The model's claim is not evidence
# --------------------------------------------------------------------------


def test_a_pass_claim_with_zero_executed_evidence_does_not_pass() -> None:
    execution = _execution(passed=True)

    assert execution.result.passed is True
    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_vacuous_truth_cannot_carry_the_decision() -> None:
    """`all([])` is True; that must not be what decides QA."""

    execution = _execution(passed=True)

    assert all(
        item.passed for item in execution.test_results
    ) is True

    assert qa_evidence_satisfied(execution.evidence) is False
    assert execution.passed is False


def test_prose_claiming_every_test_passes_does_nothing() -> None:
    execution = _execution(
        passed=True,
        summary=(
            "All tests pass. Full regression suite executed. "
            "npm test and npm run typecheck both green."
        ),
    )

    assert execution.passed is False


def test_declaring_commands_without_executing_them_is_not_evidence() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test -- src/checkout.test.ts"],
        test_results=[],
    )

    assert execution.evidence.executed_checks == 0
    assert execution.passed is False


# --------------------------------------------------------------------------
# Executed evidence decides
# --------------------------------------------------------------------------


def test_one_executed_passing_check_is_evidence() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test -- src/checkout.test.ts"],
        test_results=[_check("npm test -- src/checkout.test.ts")],
    )

    assert execution.evidence == QAEvidence(
        executed_checks=1,
        passed_checks=1,
        failed_checks=0,
        blocking_blockers=0,
        blocking_defects=0,
    )
    assert execution.passed is True


def test_one_executed_failing_check_forces_failure() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test -- src/checkout.test.ts"],
        test_results=[
            _check("npm test -- src/checkout.test.ts", passed=False)
        ],
    )

    assert execution.passed is False


def test_a_mixed_run_forces_failure() -> None:
    execution = _execution(
        passed=True,
        test_commands=["a", "b"],
        test_results=[_check("a"), _check("b", passed=False)],
    )

    assert execution.evidence.passed_checks == 1
    assert execution.evidence.failed_checks == 1
    assert execution.passed is False


def test_a_blocking_blocker_still_stops_qa() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test"],
        test_results=[_check("npm test")],
        blockers=[_external_blocker()],
    )

    assert execution.evidence.blocking_blockers == 1
    assert execution.passed is False


def test_a_demoted_blocker_does_not_stop_qa() -> None:
    """Structured blocker policy is unchanged."""

    execution = _execution(
        passed=True,
        test_commands=["npm test"],
        test_results=[_check("npm test")],
        blockers=[
            Blocker(
                message="Which currency should totals use?",
                kind=BlockerKind.HUMAN_DECISION,
                scope=BlockerScope.PROJECT,
                fixable_by_agent=False,
                requires_human_input=True,
                blocking=True,
            )
        ],
    )

    assert execution.evidence.blocking_blockers == 0
    assert execution.passed is True


@pytest.mark.parametrize("severity", sorted(BLOCKING_DEFECT_SEVERITIES))
def test_an_unresolved_blocking_defect_forces_failure(
    severity: str,
) -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test"],
        test_results=[_check("npm test")],
        defects=[_defect(severity)],
    )

    assert execution.evidence.blocking_defects == 1
    assert execution.passed is False


def test_a_low_severity_defect_does_not_force_failure() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test"],
        test_results=[_check("npm test")],
        defects=[_defect("Low")],
    )

    assert execution.passed is True


# --------------------------------------------------------------------------
# The model may withhold success, never grant it
# --------------------------------------------------------------------------


def test_a_model_failure_claim_is_not_overridden_by_green_checks() -> None:
    """One-directional authority: it can fail QA, never pass it."""

    execution = _execution(
        passed=False,
        test_commands=["npm test"],
        test_results=[_check("npm test")],
    )

    assert qa_evidence_satisfied(execution.evidence) is True
    assert execution.passed is False


def test_the_model_claim_is_recorded_but_never_sufficient() -> None:
    claimed = _execution(passed=True)
    denied = _execution(passed=False)

    assert claimed.result.passed is True
    assert claimed.passed is False
    assert denied.passed is False


# --------------------------------------------------------------------------
# Producer boundary
# --------------------------------------------------------------------------


def test_a_response_declaring_no_validation_work_is_reported() -> None:
    reason = missing_qa_evidence(
        QAResult(summary="QA passed.", passed=True, test_commands=[])
    )

    assert reason
    assert "validation" in reason.lower()


def test_a_response_declaring_validation_work_is_accepted() -> None:
    assert missing_qa_evidence(
        QAResult(
            summary="QA passed.",
            passed=True,
            test_commands=["npm test -- src/checkout.test.ts"],
        )
    ) == ""


def test_the_provider_cannot_opt_out_by_returning_empty_collections(
    tmp_path: Path,
) -> None:
    class EmptyQAProvider:
        def validate_qa(self, prompt: str) -> QAResult:
            return QAResult(
                summary="Everything passes.",
                passed=True,
                defects=[],
                test_commands=[],
                blockers=[],
            )

    execution = run_qa_validation(
        project_root=tmp_path,
        context={},
        provider=EmptyQAProvider(),
    )

    assert execution.result.passed is True
    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_the_runtime_fails_closed_when_the_producer_is_bypassed() -> None:
    """Constructed directly, with no producer validation at all."""

    execution = QAExecution(
        result=QAResult(summary="Passed.", passed=True),
        prompt="prompt",
        test_results=[],
    )

    assert execution.passed is False


# --------------------------------------------------------------------------
# The QA Gate derives readiness from evidence
# --------------------------------------------------------------------------


def _qa_state(
    qa_passed: bool = True,
    test_results: list[dict] | None = None,
    defects: list[dict] | None = None,
    blockers: list[dict] | None = None,
) -> dict:
    return {
        "status": "REVIEW_REQUIRED",
        "last_result": {
            "qa_summary": "QA validation completed.",
            "qa_model_passed": True,
            "qa_passed": qa_passed,
            "qa_test_results": (
                test_results
                if test_results is not None
                else []
            ),
            "qa_defects": defects or [],
            "qa_blockers": blockers or [],
        },
    }


def test_the_gate_is_not_ready_without_executed_evidence() -> None:
    evaluation = evaluate_qa_gate(_qa_state(qa_passed=True))

    assert evaluation.ready is False
    assert any(
        "evidence" in reason.lower() for reason in evaluation.reasons
    )


def test_the_gate_ignores_a_raw_qa_passed_flag_without_evidence() -> None:
    """Even a hand-edited or legacy state cannot open the gate."""

    state = _qa_state(qa_passed=True)
    state["last_result"]["qa_model_passed"] = True

    assert evaluate_qa_gate(state).ready is False


def test_the_gate_is_ready_when_executed_evidence_is_green() -> None:
    evaluation = evaluate_qa_gate(
        _qa_state(
            qa_passed=True,
            test_results=[_serialized("npm test")],
        )
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_the_gate_is_not_ready_when_an_executed_check_failed() -> None:
    evaluation = evaluate_qa_gate(
        _qa_state(
            qa_passed=True,
            test_results=[
                _serialized("npm test", passed=False),
            ],
        )
    )

    assert evaluation.ready is False


def test_persisted_and_reloaded_evidence_decides_identically() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm test"],
        test_results=[_check("npm test")],
    )

    reloaded = evaluate_qa_gate(
        _qa_state(
            qa_passed=execution.passed,
            test_results=[_serialized("npm test")],
        )
    )

    assert execution.passed is True
    assert reloaded.ready is True


def test_describe_qa_evidence_is_structural_only() -> None:
    evidence = describe_qa_evidence(
        test_results=[_serialized("npm test")],
        blockers=[],
        defects=[{"severity": "Critical"}],
    )

    assert evidence.executed_checks == 1
    assert evidence.blocking_defects == 1


# --------------------------------------------------------------------------
# The workflow boundary: Security must not open from nothing
# --------------------------------------------------------------------------


def _workflow_state(qa_last_result: dict) -> dict:
    return {
        "project": {"name": "Test Project", "phase": "qa"},
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": False,
            "security": False,
            "devops": False,
            "sre": False,
        },
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {
                "status": "REVIEW_REQUIRED",
                "last_result": qa_last_result,
            },
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "qa_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
    }


def test_security_cannot_open_from_a_qa_claim_without_evidence() -> None:
    """The critical workflow boundary."""

    state = _workflow_state(
        {
            "qa_summary": "Everything passes.",
            "qa_model_passed": True,
            "qa_passed": True,
            "qa_test_results": [],
            "qa_defects": [],
            "qa_blockers": [],
        }
    )

    state = update_qa_gate_from_state(state)

    assert state["qa_gate"]["status"] == "NOT_READY"

    with pytest.raises(ValueError, match="QA Gate is not ready"):
        apply_approval(state, "qa")

    assert state["agents"]["security"]["status"] == "NOT_STARTED"
    assert state["approvals"]["qa"] is False


def test_security_opens_only_after_evidence_backed_qa_approval() -> None:
    state = _workflow_state(
        {
            "qa_summary": "QA validation completed.",
            "qa_model_passed": True,
            "qa_passed": True,
            "qa_test_results": [_serialized("npm test")],
            "qa_defects": [],
            "qa_blockers": [],
        }
    )

    state = update_qa_gate_from_state(state)

    assert state["qa_gate"]["status"] == "READY_FOR_REVIEW"

    state = apply_approval(state, "qa")

    assert state["approvals"]["qa"] is True
    assert state["agents"]["security"]["status"] == "READY"
