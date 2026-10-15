"""SRE cannot declare the system production-ready.

SRE is the most structured agent in the Factory. Its execution rule already
required `observability_ready` and `incident_readiness`, and its gate
required both again plus a findings-severity policy. It looks like the
strictest boundary in the workflow.

Every one of those requirements is a boolean the agent declares about itself.
`SREExecution.passed` was `result.passed and result.observability_ready and
result.incident_readiness and all(test_results) and not blockers`, and with no
executed command `all([])` is True, so the whole decision reduced to three
model booleans - and the SRE Gate is the last engine-derived barrier before
the Production Gate.

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
from ai_factory.production_gate import evaluate_production_gate
from ai_factory.sre_evidence import (
    BLOCKING_FINDING_SEVERITIES,
    RESOLVED_FINDING_STATUS,
    SREEvidence,
    describe_sre_evidence,
    missing_sre_evidence,
    sre_evidence_satisfied,
)
from ai_factory.sre_gate import evaluate_sre_gate
from ai_factory.sre_gate_runtime import update_sre_gate_from_state
from ai_factory.sre_result import SREFinding, SREResult
from ai_factory.sre_runtime import SREExecution, run_sre_validation
from ai_factory.test_runner import CommandExecutionResult


def _check(command: str = "npm run healthcheck",
           passed: bool = True) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        returncode=0 if passed else 1,
        stdout="",
        stderr="" if passed else "probe failed",
    )


def _serialized(passed: bool = True) -> dict:
    return {
        "command": "npm run healthcheck",
        "returncode": 0 if passed else 1,
        "passed": passed,
        "stdout": "",
        "stderr": "",
    }


def _finding(
    severity: str = "Critical",
    status: str = "OPEN",
) -> SREFinding:
    return SREFinding(
        id="SRE-001",
        title="No alert on error-rate burn",
        severity=severity,
        category="observability",
        description="No alerting rule covers the error budget.",
        recommendation="Add a burn-rate alert.",
        status=status,
    )


def _external_blocker() -> Blocker:
    return Blocker(
        message="The metrics backend is unreachable.",
        kind=BlockerKind.EXTERNAL_DEPENDENCY,
        scope=BlockerScope.EXTERNAL,
        fixable_by_agent=False,
        requires_human_input=True,
        blocking=True,
    )


def _execution(
    passed: bool = True,
    observability_ready: bool = True,
    incident_readiness: bool = True,
    test_commands: list[str] | None = None,
    test_results: list[CommandExecutionResult] | None = None,
    findings: list[SREFinding] | None = None,
    blockers: list[Blocker] | None = None,
    summary: str = "Operational readiness reviewed.",
) -> SREExecution:
    return SREExecution(
        result=SREResult(
            summary=summary,
            passed=passed,
            findings=findings or [],
            test_commands=test_commands or [],
            blockers=blockers or [],
            observability_ready=observability_ready,
            incident_readiness=incident_readiness,
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
    assert execution.result.observability_ready is True
    assert execution.result.incident_readiness is True

    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_an_empty_sre_result_cannot_pass_through_vacuous_truth() -> None:
    execution = _execution()

    assert all(
        item.passed for item in execution.test_results
    ) is True

    assert sre_evidence_satisfied(execution.evidence) is False
    assert execution.passed is False


def test_prose_claiming_production_readiness_has_no_authority() -> None:
    execution = _execution(
        summary=(
            "The system is production ready. Dashboards are green, "
            "on-call rotation is staffed, runbooks are complete."
        ),
    )

    assert execution.passed is False


def test_declaring_checks_without_executing_them_is_not_evidence() -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[],
    )

    assert execution.evidence.executed_checks == 0
    assert execution.passed is False


# --------------------------------------------------------------------------
# The existing structured requirements are preserved
# --------------------------------------------------------------------------


def test_missing_observability_readiness_prevents_success() -> None:
    execution = _execution(
        observability_ready=False,
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
    )

    assert execution.evidence.observability_declared is False
    assert execution.passed is False


def test_missing_incident_readiness_prevents_success() -> None:
    execution = _execution(
        incident_readiness=False,
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
    )

    assert execution.evidence.incident_readiness_declared is False
    assert execution.passed is False


@pytest.mark.parametrize("severity", sorted(BLOCKING_FINDING_SEVERITIES))
def test_an_unresolved_blocking_finding_prevents_success(
    severity: str,
) -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
        findings=[_finding(severity=severity, status="OPEN")],
    )

    assert execution.evidence.unresolved_findings == 1
    assert execution.passed is False


def test_a_resolved_finding_does_not_prevent_success() -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
        findings=[
            _finding(
                severity="Critical",
                status=RESOLVED_FINDING_STATUS,
            )
        ],
    )

    assert execution.evidence.unresolved_findings == 0
    assert execution.passed is True


# --------------------------------------------------------------------------
# Executed evidence decides
# --------------------------------------------------------------------------


def test_complete_required_evidence_may_pass() -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
    )

    assert execution.evidence == SREEvidence(
        executed_checks=1,
        passed_checks=1,
        failed_checks=0,
        blocking_blockers=0,
        unresolved_findings=0,
        observability_declared=True,
        incident_readiness_declared=True,
    )
    assert execution.passed is True


def test_a_failed_operational_check_forces_failure() -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[_check(passed=False)],
    )

    assert execution.passed is False


def test_mixed_results_force_failure() -> None:
    execution = _execution(
        test_commands=["a", "b"],
        test_results=[_check("a"), _check("b", passed=False)],
    )

    assert execution.evidence.passed_checks == 1
    assert execution.evidence.failed_checks == 1
    assert execution.passed is False


def test_an_effective_blocker_prevents_success() -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
        blockers=[_external_blocker()],
    )

    assert execution.evidence.blocking_blockers == 1
    assert execution.passed is False


def test_a_demoted_blocker_does_not_prevent_success() -> None:
    execution = _execution(
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
        blockers=[
            Blocker(
                message="Which on-call rotation tool should be used?",
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
        test_commands=["npm run healthcheck"],
        test_results=[_check()],
    )

    assert sre_evidence_satisfied(execution.evidence) is True
    assert execution.passed is False


# --------------------------------------------------------------------------
# Producer boundary and runtime enforcement
# --------------------------------------------------------------------------


def test_a_response_declaring_no_operational_work_is_reported() -> None:
    reason = missing_sre_evidence(
        SREResult(
            summary="Production ready.",
            passed=True,
            test_commands=[],
            observability_ready=True,
            incident_readiness=True,
        )
    )

    assert reason
    assert "validation" in reason.lower()


def test_a_response_declaring_operational_work_is_accepted() -> None:
    assert missing_sre_evidence(
        SREResult(
            summary="Production ready.",
            passed=True,
            test_commands=["npm run healthcheck"],
            observability_ready=True,
            incident_readiness=True,
        )
    ) == ""


def test_the_provider_cannot_bypass_evidence_with_empty_collections(
    tmp_path,
) -> None:
    class EmptySREProvider:
        def validate_sre(self, prompt: str) -> SREResult:
            return SREResult(
                summary="The system is production ready.",
                passed=True,
                findings=[],
                test_commands=[],
                blockers=[],
                observability_ready=True,
                incident_readiness=True,
            )

    execution = run_sre_validation(
        project_root=tmp_path,
        context={},
        provider=EmptySREProvider(),
    )

    assert execution.result.passed is True
    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_the_runtime_fails_closed_when_the_producer_is_bypassed() -> None:
    execution = SREExecution(
        result=SREResult(
            summary="Ready.",
            passed=True,
            observability_ready=True,
            incident_readiness=True,
        ),
        prompt="prompt",
        test_results=[],
    )

    assert execution.passed is False


# --------------------------------------------------------------------------
# The SRE Gate derives readiness from evidence
# --------------------------------------------------------------------------


def _sre_state(
    sre_passed: bool = True,
    observability_ready: bool = True,
    incident_readiness: bool = True,
    test_results: list[dict] | None = None,
    findings: list[dict] | None = None,
    blockers: list[dict] | None = None,
) -> dict:
    return {
        "status": "REVIEW_REQUIRED",
        "last_result": {
            "sre_summary": "Operational readiness reviewed.",
            "sre_model_passed": True,
            "sre_passed": sre_passed,
            "sre_test_results": (
                test_results if test_results is not None else []
            ),
            "sre_findings": findings or [],
            "sre_blockers": blockers or [],
            "observability_ready": observability_ready,
            "incident_readiness": incident_readiness,
        },
    }


def test_the_gate_is_not_ready_without_executed_evidence() -> None:
    evaluation = evaluate_sre_gate(_sre_state())

    assert evaluation.ready is False
    assert any(
        "evidence" in reason.lower() for reason in evaluation.reasons
    )


def test_a_raw_persisted_sre_passed_cannot_override_missing_evidence(
) -> None:
    assert evaluate_sre_gate(
        _sre_state(sre_passed=True)
    ).ready is False


def test_the_gate_is_ready_when_all_required_evidence_is_green() -> None:
    evaluation = evaluate_sre_gate(
        _sre_state(test_results=[_serialized()])
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_the_gate_still_refuses_missing_observability() -> None:
    evaluation = evaluate_sre_gate(
        _sre_state(
            observability_ready=False,
            test_results=[_serialized()],
        )
    )

    assert evaluation.ready is False
    assert "Observability is not ready." in evaluation.reasons


def test_the_gate_still_refuses_missing_incident_readiness() -> None:
    evaluation = evaluate_sre_gate(
        _sre_state(
            incident_readiness=False,
            test_results=[_serialized()],
        )
    )

    assert evaluation.ready is False
    assert (
        "Incident readiness is not sufficient." in evaluation.reasons
    )


def test_the_gate_still_refuses_unresolved_blocking_findings() -> None:
    evaluation = evaluate_sre_gate(
        _sre_state(
            test_results=[_serialized()],
            findings=[{"severity": "Critical", "status": "OPEN"}],
        )
    )

    assert evaluation.ready is False


def test_the_gate_refuses_a_failed_check() -> None:
    assert evaluate_sre_gate(
        _sre_state(test_results=[_serialized(passed=False)])
    ).ready is False


def test_persisted_and_reloaded_evidence_decides_identically() -> None:
    live = describe_sre_evidence(
        test_results=[_check()],
        blockers=[],
        findings=[_finding(severity="High", status="OPEN")],
        observability_ready=True,
        incident_readiness=True,
    )

    stored = describe_sre_evidence(
        test_results=[_serialized()],
        blockers=[],
        findings=[{"severity": "High", "status": "OPEN"}],
        observability_ready=True,
        incident_readiness=True,
    )

    assert live == stored


# --------------------------------------------------------------------------
# The last boundary: production must not open from nothing
# --------------------------------------------------------------------------


def _workflow_state(sre_last_result: dict) -> dict:
    return {
        "project": {"name": "Test Project", "phase": "sre"},
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": True,
            "devops": True,
            "sre": False,
            "production_deployment": False,
        },
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "APPROVED"},
            "devops": {"status": "APPROVED"},
            "sre": {
                "status": "REVIEW_REQUIRED",
                "last_result": sre_last_result,
            },
        },
        "sre_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
    }


def test_production_cannot_open_from_an_evidence_free_sre_pass() -> None:
    """The final trust boundary."""

    state = _workflow_state(
        {
            "sre_summary": "The system is production ready.",
            "sre_model_passed": True,
            "sre_passed": True,
            "sre_test_results": [],
            "sre_findings": [],
            "sre_blockers": [],
            "observability_ready": True,
            "incident_readiness": True,
        }
    )

    state = update_sre_gate_from_state(state)

    assert state["sre_gate"]["status"] == "NOT_READY"

    with pytest.raises(ValueError, match="SRE Gate is not ready"):
        apply_approval(state, "sre")

    assert state["approvals"]["sre"] is False
    assert evaluate_production_gate(state).ready is False


def test_production_opens_after_evidence_backed_sre_approval() -> None:
    state = _workflow_state(
        {
            "sre_summary": "Operational readiness reviewed.",
            "sre_model_passed": True,
            "sre_passed": True,
            "sre_test_results": [_serialized()],
            "sre_findings": [],
            "sre_blockers": [],
            "observability_ready": True,
            "incident_readiness": True,
        }
    )

    state = update_sre_gate_from_state(state)

    assert state["sre_gate"]["status"] == "READY_FOR_REVIEW"

    state = apply_approval(state, "sre")

    assert state["approvals"]["sre"] is True
    assert state["agents"]["sre"]["status"] == "APPROVED"
    assert state["sre_gate"]["status"] == "APPROVED"

    assert evaluate_production_gate(state).ready is True


# --------------------------------------------------------------------------
# Retry lifecycle, now bounded
# --------------------------------------------------------------------------


def test_sre_is_still_reselected_after_failure_but_is_now_budgeted() -> None:
    """The selection rule is unchanged; what stops the loop is the budget.

    `get_next_agent` still returns a FAILED SRE - the orchestrator was
    deliberately not touched, because the same rule serves every agent. What
    changed is that SRE now carries a persisted budget, so the re-selection
    is refused before a provider call once that budget is spent.
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
            "devops": {"status": "APPROVED"},
            "sre": {"status": "FAILED"},
        },
    }

    assert get_next_agent(state) == "sre"
    assert "sre" in BUDGETED_AGENTS
