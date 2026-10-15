"""Security cannot clear itself.

`SecurityExecution.passed` was `result.passed and all(test_results) and not
blockers`. With no executed check, `all([])` is True and the decision reduced
to `result.passed` - the Security agent's own verdict on its own review. The
Security Gate then read `security_passed`, became READY_FOR_REVIEW, and the
last thing between "security is fine" and DevOps was a human reading a
summary.

The agent may propose checks, findings, severities and remediations. Whether
the security phase passed is decided by what the engine executed.
"""

import pytest

from ai_factory.approval_runtime import apply_approval
from ai_factory.blocker_contract import (
    Blocker,
    BlockerKind,
    BlockerScope,
)
from ai_factory.security_evidence import (
    BLOCKING_FINDING_SEVERITIES,
    RESOLVED_FINDING_STATUS,
    SecurityEvidence,
    describe_security_evidence,
    missing_security_evidence,
    security_evidence_satisfied,
)
from ai_factory.security_gate import evaluate_security_gate
from ai_factory.security_gate_runtime import (
    update_security_gate_from_state,
)
from ai_factory.security_result import SecurityFinding, SecurityResult
from ai_factory.security_runtime import (
    SecurityExecution,
    run_security_validation,
)
from ai_factory.test_runner import CommandExecutionResult


def _check(command: str = "npm audit --audit-level=high",
           passed: bool = True) -> CommandExecutionResult:
    return CommandExecutionResult(
        command=command,
        returncode=0 if passed else 1,
        stdout="",
        stderr="" if passed else "vulnerabilities found",
    )


def _serialized(passed: bool = True) -> dict:
    return {
        "command": "npm audit --audit-level=high",
        "returncode": 0 if passed else 1,
        "passed": passed,
        "stdout": "",
        "stderr": "",
    }


def _finding(
    severity: str = "Critical",
    status: str = "OPEN",
) -> SecurityFinding:
    return SecurityFinding(
        id="SEC-001",
        title="Session cookie is not marked Secure",
        severity=severity,
        affected_component="src/auth/session.ts",
        description="The session cookie is issued without Secure.",
        impact="Session hijacking over plaintext transport.",
        evidence="Set-Cookie header lacks the Secure attribute.",
        recommended_remediation="Set Secure and SameSite on the cookie.",
        priority="P1",
        status=status,
    )


def _external_blocker() -> Blocker:
    return Blocker(
        message="The dependency advisory database is unreachable.",
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
    findings: list[SecurityFinding] | None = None,
    blockers: list[Blocker] | None = None,
    summary: str = "Security review completed.",
) -> SecurityExecution:
    return SecurityExecution(
        result=SecurityResult(
            summary=summary,
            passed=passed,
            findings=findings or [],
            test_commands=test_commands or [],
            blockers=blockers or [],
        ),
        prompt="prompt",
        test_results=test_results or [],
    )


# --------------------------------------------------------------------------
# The claim is not evidence
# --------------------------------------------------------------------------


def test_a_pass_claim_with_zero_executed_evidence_does_not_pass() -> None:
    execution = _execution(passed=True)

    assert execution.result.passed is True
    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_an_empty_result_cannot_pass_through_vacuous_truth() -> None:
    execution = _execution(passed=True)

    assert all(
        item.passed for item in execution.test_results
    ) is True

    assert security_evidence_satisfied(execution.evidence) is False
    assert execution.passed is False


def test_prose_about_excellent_security_does_nothing() -> None:
    execution = _execution(
        passed=True,
        summary=(
            "Security is excellent. No vulnerabilities. "
            "npm audit and semgrep both clean."
        ),
    )

    assert execution.passed is False


def test_declaring_checks_without_executing_them_is_not_evidence() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit --audit-level=high"],
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
        test_commands=["npm audit --audit-level=high"],
        test_results=[_check()],
    )

    assert execution.evidence == SecurityEvidence(
        executed_checks=1,
        passed_checks=1,
        failed_checks=0,
        blocking_blockers=0,
        unresolved_findings=0,
    )
    assert execution.passed is True


def test_one_failing_security_check_forces_failure() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit --audit-level=high"],
        test_results=[_check(passed=False)],
    )

    assert execution.passed is False


def test_mixed_results_force_failure() -> None:
    execution = _execution(
        passed=True,
        test_commands=["a", "b"],
        test_results=[_check("a"), _check("b", passed=False)],
    )

    assert execution.evidence.passed_checks == 1
    assert execution.evidence.failed_checks == 1
    assert execution.passed is False


def test_an_effective_blocker_prevents_success() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit"],
        test_results=[_check()],
        blockers=[_external_blocker()],
    )

    assert execution.evidence.blocking_blockers == 1
    assert execution.passed is False


def test_a_demoted_blocker_does_not_prevent_success() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit"],
        test_results=[_check()],
        blockers=[
            Blocker(
                message="Which threat model applies to the MVP?",
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
# Findings, under the current severity policy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("severity", sorted(BLOCKING_FINDING_SEVERITIES))
def test_an_unresolved_blocking_finding_prevents_success(
    severity: str,
) -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit"],
        test_results=[_check()],
        findings=[_finding(severity=severity, status="OPEN")],
    )

    assert execution.evidence.unresolved_findings == 1
    assert execution.passed is False


def test_a_resolved_blocking_finding_does_not_prevent_success() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit"],
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


def test_a_low_severity_finding_does_not_prevent_success() -> None:
    execution = _execution(
        passed=True,
        test_commands=["npm audit"],
        test_results=[_check()],
        findings=[_finding(severity="Low", status="OPEN")],
    )

    assert execution.passed is True


# --------------------------------------------------------------------------
# The model may withhold success, never grant it
# --------------------------------------------------------------------------


def test_a_model_failure_claim_is_not_overridden_by_green_checks() -> None:
    execution = _execution(
        passed=False,
        test_commands=["npm audit"],
        test_results=[_check()],
    )

    assert security_evidence_satisfied(execution.evidence) is True
    assert execution.passed is False


def test_the_model_claim_alone_never_opens_anything() -> None:
    assert _execution(passed=True).passed is False
    assert _execution(passed=False).passed is False


# --------------------------------------------------------------------------
# Producer boundary and runtime enforcement
# --------------------------------------------------------------------------


def test_a_response_declaring_no_security_work_is_reported() -> None:
    reason = missing_security_evidence(
        SecurityResult(
            summary="Security passed.",
            passed=True,
            test_commands=[],
        )
    )

    assert reason
    assert "validation" in reason.lower()


def test_a_response_declaring_security_work_is_accepted() -> None:
    assert missing_security_evidence(
        SecurityResult(
            summary="Security passed.",
            passed=True,
            test_commands=["npm audit --audit-level=high"],
        )
    ) == ""


def test_the_provider_cannot_opt_out_with_empty_collections(
    tmp_path,
) -> None:
    class EmptySecurityProvider:
        def validate_security(self, prompt: str) -> SecurityResult:
            return SecurityResult(
                summary="No vulnerabilities found.",
                passed=True,
                findings=[],
                test_commands=[],
                blockers=[],
            )

    execution = run_security_validation(
        project_root=tmp_path,
        context={},
        provider=EmptySecurityProvider(),
    )

    assert execution.result.passed is True
    assert execution.passed is False
    assert execution.evidence.executed_checks == 0


def test_the_runtime_fails_closed_when_the_producer_is_bypassed() -> None:
    execution = SecurityExecution(
        result=SecurityResult(summary="Passed.", passed=True),
        prompt="prompt",
        test_results=[],
    )

    assert execution.passed is False


# --------------------------------------------------------------------------
# The Security Gate derives readiness from evidence
# --------------------------------------------------------------------------


def _security_state(
    security_passed: bool = True,
    test_results: list[dict] | None = None,
    findings: list[dict] | None = None,
    blockers: list[dict] | None = None,
) -> dict:
    return {
        "status": "REVIEW_REQUIRED",
        "last_result": {
            "security_summary": "Security review completed.",
            "security_model_passed": True,
            "security_passed": security_passed,
            "security_test_results": (
                test_results if test_results is not None else []
            ),
            "security_findings": findings or [],
            "security_blockers": blockers or [],
        },
    }


def test_the_gate_is_not_ready_without_executed_evidence() -> None:
    evaluation = evaluate_security_gate(_security_state())

    assert evaluation.ready is False
    assert any(
        "evidence" in reason.lower() for reason in evaluation.reasons
    )


def test_the_gate_ignores_a_raw_security_passed_flag() -> None:
    """A legacy, restored or hand-edited state cannot open the gate."""

    assert evaluate_security_gate(
        _security_state(security_passed=True)
    ).ready is False


def test_the_gate_is_ready_when_executed_evidence_is_green() -> None:
    evaluation = evaluate_security_gate(
        _security_state(test_results=[_serialized()])
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_the_gate_is_not_ready_when_a_check_failed() -> None:
    assert evaluate_security_gate(
        _security_state(test_results=[_serialized(passed=False)])
    ).ready is False


def test_the_gate_still_blocks_unresolved_blocking_findings() -> None:
    evaluation = evaluate_security_gate(
        _security_state(
            test_results=[_serialized()],
            findings=[{"severity": "Critical", "status": "OPEN"}],
        )
    )

    assert evaluation.ready is False


def test_persisted_and_reloaded_evidence_decides_identically() -> None:
    live = describe_security_evidence(
        test_results=[_check()],
        blockers=[],
        findings=[_finding(severity="Critical", status="OPEN")],
    )

    stored = describe_security_evidence(
        test_results=[_serialized()],
        blockers=[],
        findings=[{"severity": "Critical", "status": "OPEN"}],
    )

    assert live == stored


# --------------------------------------------------------------------------
# The workflow boundary: DevOps must not open from nothing
# --------------------------------------------------------------------------


def _workflow_state(security_last_result: dict) -> dict:
    return {
        "project": {"name": "Test Project", "phase": "security"},
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": True,
            "security": False,
            "devops": False,
            "sre": False,
        },
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {
                "status": "REVIEW_REQUIRED",
                "last_result": security_last_result,
            },
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "security_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
    }


def test_devops_cannot_open_from_a_security_claim_without_evidence(
) -> None:
    state = _workflow_state(
        {
            "security_summary": "No vulnerabilities found.",
            "security_model_passed": True,
            "security_passed": True,
            "security_test_results": [],
            "security_findings": [],
            "security_blockers": [],
        }
    )

    state = update_security_gate_from_state(state)

    assert state["security_gate"]["status"] == "NOT_READY"

    with pytest.raises(ValueError, match="Security Gate is not ready"):
        apply_approval(state, "security")

    assert state["agents"]["devops"]["status"] == "NOT_STARTED"
    assert state["approvals"]["security"] is False


def test_devops_opens_after_evidence_backed_security_approval() -> None:
    state = _workflow_state(
        {
            "security_summary": "Security review completed.",
            "security_model_passed": True,
            "security_passed": True,
            "security_test_results": [_serialized()],
            "security_findings": [],
            "security_blockers": [],
        }
    )

    state = update_security_gate_from_state(state)

    assert state["security_gate"]["status"] == "READY_FOR_REVIEW"

    state = apply_approval(state, "security")

    assert state["approvals"]["security"] is True
    assert state["agents"]["devops"]["status"] == "READY"
