"""DevOps cannot certify its own deployment readiness.

DevOps is not shaped like QA and Security. Its gate already refuses an empty
`rollback_strategy` and a `deployment_ready` that is not True, so it looks
stricter. It is not: both of those are declared by the model. The extra
checks raise what the agent must *say*, not what the engine *observes*.

Underneath, the same collapse was present. `DevOpsExecution.passed` was
`result.passed and result.deployment_ready and all(test_results) and not
blockers`, and with no executed command `all([])` is True, so the decision
reduced to two model booleans and a non-empty string.

Every existing requirement is kept. What is added is the one thing that was
missing: something the engine actually ran.
"""

import pytest

from ai_factory.approval_runtime import apply_approval
from ai_factory.blocker_contract import (
    Blocker,
    BlockerKind,
    BlockerScope,
)
from ai_factory.devops_evidence import (
    DevOpsEvidence,
    describe_devops_evidence,
    devops_evidence_satisfied,
    missing_devops_evidence,
)
from ai_factory.devops_gate import evaluate_devops_gate
from ai_factory.devops_gate_runtime import (
    update_devops_gate_from_state,
)
from ai_factory.devops_result import DevOpsChange, DevOpsResult
from ai_factory.devops_runtime import (
    DevOpsExecution,
    run_devops_validation,
)
from ai_factory.test_runner import CommandExecutionResult


ROLLBACK = "Redeploy the previous image tag and run prisma migrate resolve."


def _check(command: str = "npm run build",
           passed: bool = True) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        returncode=0 if passed else 1,
        stdout="",
        stderr="" if passed else "build failed",
    )


def _serialized(passed: bool = True) -> dict:
    return {
        "command": "npm run build",
        "returncode": 0 if passed else 1,
        "passed": passed,
        "stdout": "",
        "stderr": "",
    }


def _external_blocker() -> Blocker:
    return Blocker(
        message="The container registry is unreachable.",
        kind=BlockerKind.EXTERNAL_DEPENDENCY,
        scope=BlockerScope.EXTERNAL,
        fixable_by_agent=False,
        requires_human_input=True,
        blocking=True,
    )


def _execution(
    passed: bool = True,
    deployment_ready: bool = True,
    rollback_strategy: str = ROLLBACK,
    test_commands: list[str] | None = None,
    test_results: list[CommandExecutionResult] | None = None,
    blockers: list[Blocker] | None = None,
    summary: str = "Deployment pipeline prepared.",
) -> DevOpsExecution:
    return DevOpsExecution(
        result=DevOpsResult(
            summary=summary,
            passed=passed,
            changes=[
                DevOpsChange(
                    path="Dockerfile",
                    description="Container image definition.",
                    category="containerization",
                )
            ],
            test_commands=test_commands or [],
            blockers=blockers or [],
            deployment_ready=deployment_ready,
            rollback_strategy=rollback_strategy,
        ),
        prompt="prompt",
        test_results=test_results or [],
    )


# --------------------------------------------------------------------------
# Model assertions are not evidence
# --------------------------------------------------------------------------


def test_a_pass_claim_with_zero_executed_evidence_does_not_pass() -> None:
    execution = _execution()

    assert execution.result.passed is True
    assert execution.result.deployment_ready is True
    assert execution.result.rollback_strategy

    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_an_empty_devops_result_cannot_pass_through_vacuous_truth(
) -> None:
    execution = _execution()

    assert all(
        item.passed for item in execution.test_results
    ) is True

    assert devops_evidence_satisfied(execution.evidence) is False
    assert execution.passed is False


def test_prose_claiming_a_successful_deployment_has_no_authority() -> None:
    execution = _execution(
        summary=(
            "Deployment succeeded. Pipeline is green. "
            "Rollback verified in staging."
        ),
    )

    assert execution.passed is False


def test_declaring_commands_without_executing_them_is_not_evidence(
) -> None:
    execution = _execution(
        test_commands=["npm run build"],
        test_results=[],
    )

    assert execution.evidence.executed_checks == 0
    assert execution.passed is False


# --------------------------------------------------------------------------
# The existing structured requirements are preserved
# --------------------------------------------------------------------------


def test_missing_deployment_evidence_cannot_pass() -> None:
    execution = _execution(
        deployment_ready=False,
        test_commands=["npm run build"],
        test_results=[_check()],
    )

    assert execution.evidence.deployment_declared is False
    assert execution.passed is False


def test_missing_rollback_evidence_cannot_pass() -> None:
    execution = _execution(
        rollback_strategy="",
        test_commands=["npm run build"],
        test_results=[_check()],
    )

    assert execution.evidence.rollback_declared is False
    assert execution.passed is False


def test_a_whitespace_rollback_strategy_is_not_a_strategy() -> None:
    execution = _execution(
        rollback_strategy="   ",
        test_commands=["npm run build"],
        test_results=[_check()],
    )

    assert execution.evidence.rollback_declared is False
    assert execution.passed is False


# --------------------------------------------------------------------------
# Executed evidence decides
# --------------------------------------------------------------------------


def test_complete_required_evidence_may_pass() -> None:
    execution = _execution(
        test_commands=["npm run build"],
        test_results=[_check()],
    )

    assert execution.evidence == DevOpsEvidence(
        executed_checks=1,
        passed_checks=1,
        failed_checks=0,
        blocking_blockers=0,
        deployment_declared=True,
        rollback_declared=True,
    )
    assert execution.passed is True


def test_a_failed_executed_check_forces_failure() -> None:
    execution = _execution(
        test_commands=["npm run build"],
        test_results=[_check(passed=False)],
    )

    assert execution.passed is False


def test_mixed_check_results_force_failure() -> None:
    execution = _execution(
        test_commands=["a", "b"],
        test_results=[_check("a"), _check("b", passed=False)],
    )

    assert execution.evidence.passed_checks == 1
    assert execution.evidence.failed_checks == 1
    assert execution.passed is False


def test_an_effective_blocker_prevents_success() -> None:
    execution = _execution(
        test_commands=["npm run build"],
        test_results=[_check()],
        blockers=[_external_blocker()],
    )

    assert execution.evidence.blocking_blockers == 1
    assert execution.passed is False


def test_a_demoted_blocker_does_not_prevent_success() -> None:
    execution = _execution(
        test_commands=["npm run build"],
        test_results=[_check()],
        blockers=[
            Blocker(
                message="Which cloud region should host staging?",
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


# --------------------------------------------------------------------------
# The model may withhold success, never grant it
# --------------------------------------------------------------------------


def test_a_model_failure_claim_is_not_overridden_by_green_evidence(
) -> None:
    execution = _execution(
        passed=False,
        test_commands=["npm run build"],
        test_results=[_check()],
    )

    assert devops_evidence_satisfied(execution.evidence) is True
    assert execution.passed is False


# --------------------------------------------------------------------------
# Producer boundary and runtime enforcement
# --------------------------------------------------------------------------


def test_a_response_declaring_no_devops_work_is_reported() -> None:
    reason = missing_devops_evidence(
        DevOpsResult(
            summary="Deployment ready.",
            passed=True,
            test_commands=[],
            deployment_ready=True,
            rollback_strategy=ROLLBACK,
        )
    )

    assert reason
    assert "validation" in reason.lower()


def test_a_response_declaring_devops_work_is_accepted() -> None:
    assert missing_devops_evidence(
        DevOpsResult(
            summary="Deployment ready.",
            passed=True,
            test_commands=["npm run build"],
            deployment_ready=True,
            rollback_strategy=ROLLBACK,
        )
    ) == ""


def test_the_provider_cannot_bypass_evidence_with_empty_collections(
    tmp_path,
) -> None:
    class EmptyDevOpsProvider:
        def validate_devops(self, prompt: str) -> DevOpsResult:
            return DevOpsResult(
                summary="Deployment pipeline is ready.",
                passed=True,
                changes=[],
                test_commands=[],
                blockers=[],
                deployment_ready=True,
                rollback_strategy=ROLLBACK,
            )

    execution = run_devops_validation(
        project_root=tmp_path,
        context={},
        provider=EmptyDevOpsProvider(),
    )

    assert execution.result.passed is True
    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_the_runtime_fails_closed_when_the_producer_is_bypassed() -> None:
    execution = DevOpsExecution(
        result=DevOpsResult(
            summary="Ready.",
            passed=True,
            deployment_ready=True,
            rollback_strategy=ROLLBACK,
        ),
        prompt="prompt",
        test_results=[],
    )

    assert execution.passed is False


# --------------------------------------------------------------------------
# The DevOps Gate derives readiness from evidence
# --------------------------------------------------------------------------


def _devops_state(
    devops_passed: bool = True,
    deployment_ready: bool = True,
    rollback_strategy: str = ROLLBACK,
    test_results: list[dict] | None = None,
    blockers: list[dict] | None = None,
) -> dict:
    return {
        "status": "REVIEW_REQUIRED",
        "last_result": {
            "devops_summary": "Deployment pipeline prepared.",
            "devops_model_passed": True,
            "devops_passed": devops_passed,
            "devops_test_results": (
                test_results if test_results is not None else []
            ),
            "devops_changes": [],
            "devops_blockers": blockers or [],
            "deployment_ready": deployment_ready,
            "rollback_strategy": rollback_strategy,
        },
    }


def test_the_gate_is_not_ready_without_executed_evidence() -> None:
    evaluation = evaluate_devops_gate(_devops_state())

    assert evaluation.ready is False
    assert any(
        "evidence" in reason.lower() for reason in evaluation.reasons
    )


def test_a_raw_persisted_devops_passed_cannot_override_missing_evidence(
) -> None:
    assert evaluate_devops_gate(
        _devops_state(devops_passed=True)
    ).ready is False


def test_the_gate_is_ready_when_all_required_evidence_is_green() -> None:
    evaluation = evaluate_devops_gate(
        _devops_state(test_results=[_serialized()])
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_the_gate_still_refuses_a_missing_rollback_strategy() -> None:
    evaluation = evaluate_devops_gate(
        _devops_state(
            rollback_strategy="",
            test_results=[_serialized()],
        )
    )

    assert evaluation.ready is False
    assert "Rollback strategy is missing." in evaluation.reasons


def test_the_gate_still_refuses_deployment_not_ready() -> None:
    evaluation = evaluate_devops_gate(
        _devops_state(
            deployment_ready=False,
            test_results=[_serialized()],
        )
    )

    assert evaluation.ready is False
    assert "Deployment is not ready." in evaluation.reasons


def test_the_gate_refuses_a_failed_check() -> None:
    assert evaluate_devops_gate(
        _devops_state(test_results=[_serialized(passed=False)])
    ).ready is False


def test_persisted_and_reloaded_evidence_decides_identically() -> None:
    live = describe_devops_evidence(
        test_results=[_check()],
        blockers=[],
        deployment_ready=True,
        rollback_strategy=ROLLBACK,
    )

    stored = describe_devops_evidence(
        test_results=[_serialized()],
        blockers=[],
        deployment_ready=True,
        rollback_strategy=ROLLBACK,
    )

    assert live == stored


# --------------------------------------------------------------------------
# The workflow boundary: SRE must not open from nothing
# --------------------------------------------------------------------------


def _workflow_state(devops_last_result: dict) -> dict:
    return {
        "project": {"name": "Test Project", "phase": "devops"},
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": True,
            "devops": False,
            "sre": False,
        },
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "APPROVED"},
            "devops": {
                "status": "REVIEW_REQUIRED",
                "last_result": devops_last_result,
            },
            "sre": {"status": "NOT_STARTED"},
        },
        "devops_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
    }


def test_sre_cannot_open_from_an_evidence_free_devops_pass() -> None:
    state = _workflow_state(
        {
            "devops_summary": "Deployment pipeline is ready.",
            "devops_model_passed": True,
            "devops_passed": True,
            "devops_test_results": [],
            "devops_changes": [],
            "devops_blockers": [],
            "deployment_ready": True,
            "rollback_strategy": ROLLBACK,
        }
    )

    state = update_devops_gate_from_state(state)

    assert state["devops_gate"]["status"] == "NOT_READY"

    with pytest.raises(ValueError, match="DevOps Gate is not ready"):
        apply_approval(state, "devops")

    assert state["agents"]["sre"]["status"] == "NOT_STARTED"
    assert state["approvals"]["devops"] is False


def test_sre_opens_after_evidence_backed_devops_approval() -> None:
    state = _workflow_state(
        {
            "devops_summary": "Deployment pipeline prepared.",
            "devops_model_passed": True,
            "devops_passed": True,
            "devops_test_results": [_serialized()],
            "devops_changes": [],
            "devops_blockers": [],
            "deployment_ready": True,
            "rollback_strategy": ROLLBACK,
        }
    )

    state = update_devops_gate_from_state(state)

    assert state["devops_gate"]["status"] == "READY_FOR_REVIEW"

    state = apply_approval(state, "devops")

    assert state["approvals"]["devops"] is True
    assert state["agents"]["sre"]["status"] == "READY"


# --------------------------------------------------------------------------
# The retry lifecycle, confirmed but deliberately not fixed here
# --------------------------------------------------------------------------


def test_devops_is_reselected_after_failure_but_now_bounded() -> None:
    """Re-selection is still how a retry happens; it is now budgeted.

    This began as documentation that DevOps was unbounded. The bound landed
    in the following mission, so the test now pins the property that
    replaced it.
    """

    from ai_factory.orchestrator import get_next_agent
    from ai_factory.replan_guard import BUDGETED_AGENTS

    state = {
        "project": {"name": "P"},
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "APPROVED"},
            "devops": {"status": "FAILED"},
            "sre": {"status": "NOT_STARTED"},
        },
    }

    assert get_next_agent(state) == "devops"
    assert "devops" in BUDGETED_AGENTS
