"""Security may retry. It may not retry forever.

Making Security success depend on executed evidence turned a latent defect
into an observable one: with the mock provider declaring no checks, Security
began to fail, `get_next_agent` kept re-selecting it, and the test suite hung.
Security had no bound of its own, exactly as QA had none.

Security is bounded for the same structural reason as QA and not by analogy:
`SecurityResult` carries no file changes, so a Security cycle re-reviews a
workspace that Security itself never modified. A repeated cycle reads
identical artifacts with an identical prompt.
"""

from pathlib import Path

import pytest

from ai_factory.providers import ModelProvider, SecurityProvider
from ai_factory.qa_retry_guard import MAX_QA_RETRIES, assert_qa_retry_budget
from ai_factory.replan_guard import (
    MAX_DEVELOPER_REPLANS,
    ReplanBudgetResetError,
    assert_replan_budget,
    reset_replan_budget,
)
from ai_factory.security_result import SecurityFinding, SecurityResult
from ai_factory.security_retry_guard import (
    MAX_SECURITY_RETRIES,
    NonConvergingSecurityError,
    advance_security_retry_state,
    assert_security_retry_budget,
    build_security_failure_signature,
    get_security_failure_signature,
    get_security_repeated_failures,
    get_security_retry_count,
)
from ai_factory.runtime import run_next_agent, run_workflow
from ai_factory.state import load_state, save_state
from ai_factory.transitions import retry_agent


FAILED_CHECK = {
    "command": "npm audit --audit-level=high",
    "returncode": 1,
    "passed": False,
    "stdout": "",
    "stderr": "vulnerabilities found",
}

PASSING_CHECK = {
    "command": "npm audit --audit-level=high",
    "returncode": 0,
    "passed": True,
    "stdout": "",
    "stderr": "",
}


def _security_last_result(
    retry_count: int = 0,
    repeated: int = 0,
    signature: str = "",
    test_results: list[dict] | None = None,
    findings: list[dict] | None = None,
    blockers: list[dict] | None = None,
    security_passed: bool = False,
) -> dict:
    return {
        "security_summary": "Security review completed.",
        "security_model_passed": security_passed,
        "security_passed": security_passed,
        "security_test_results": (
            test_results if test_results is not None else [FAILED_CHECK]
        ),
        "security_findings": findings or [],
        "security_blockers": blockers or [],
        "security_retry_count": retry_count,
        "security_repeated_failures": repeated,
        "security_failure_signature": signature,
    }


def _state(security_status: str = "FAILED", **kwargs) -> dict:
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
                "status": security_status,
                "last_result": _security_last_result(**kwargs),
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


# --------------------------------------------------------------------------
# The bound
# --------------------------------------------------------------------------


def test_a_first_security_failure_may_be_retried() -> None:
    assert_security_retry_budget(_state(retry_count=1))


def test_the_bound_is_finite_and_conservative() -> None:
    assert MAX_SECURITY_RETRIES == 2
    assert MAX_SECURITY_RETRIES < MAX_DEVELOPER_REPLANS


def test_persistent_security_failure_cannot_loop_forever() -> None:
    with pytest.raises(
        NonConvergingSecurityError,
        match="NON_CONVERGING_SECURITY",
    ):
        assert_security_retry_budget(
            _state(retry_count=MAX_SECURITY_RETRIES)
        )


def test_an_identical_repeated_failure_stops_earlier() -> None:
    with pytest.raises(NonConvergingSecurityError):
        assert_security_retry_budget(
            _state(retry_count=1, repeated=1)
        )


def test_the_guard_reads_only_persisted_counters() -> None:
    assert_security_retry_budget(_state(retry_count=0, repeated=0))
    assert_security_retry_budget(_state(retry_count=1, repeated=0))


# --------------------------------------------------------------------------
# Structured signature only
# --------------------------------------------------------------------------


def test_the_signature_uses_failed_commands_and_engine_reasons() -> None:
    signature = build_security_failure_signature(
        _security_last_result(test_results=[FAILED_CHECK])
    )

    assert "failed_checks" in signature
    assert "npm audit --audit-level=high" in signature


def test_the_signature_ignores_prose_and_finding_identity() -> None:
    first = _security_last_result(test_results=[FAILED_CHECK])
    first["security_summary"] = "Three injection vectors in the auth layer."

    second = _security_last_result(test_results=[FAILED_CHECK])
    second["security_summary"] = "An entirely different narrative."
    second["security_findings"] = [
        {
            "id": "SEC-999",
            "title": "Renamed finding",
            "description": "Rewritten description.",
            "severity": "Low",
            "status": "OPEN",
        }
    ]

    assert build_security_failure_signature(first) == (
        build_security_failure_signature(second)
    )


def test_unresolved_blocking_findings_change_the_signature() -> None:
    without = build_security_failure_signature(
        _security_last_result(test_results=[FAILED_CHECK])
    )

    with_finding = build_security_failure_signature(
        _security_last_result(
            test_results=[FAILED_CHECK],
            findings=[{"severity": "Critical", "status": "OPEN"}],
        )
    )

    assert without != with_finding
    assert "unresolved_findings:1" in with_finding


def test_missing_evidence_has_its_own_structural_signature() -> None:
    signature = build_security_failure_signature(
        _security_last_result(test_results=[])
    )

    assert "no_evidence" in signature


def test_a_different_failing_command_is_a_different_signature() -> None:
    other = dict(FAILED_CHECK)
    other["command"] = "npm audit --audit-level=moderate"

    assert build_security_failure_signature(
        _security_last_result(test_results=[FAILED_CHECK])
    ) != build_security_failure_signature(
        _security_last_result(test_results=[other])
    )


def test_a_successful_cycle_has_no_signature() -> None:
    assert build_security_failure_signature(
        _security_last_result(
            test_results=[PASSING_CHECK],
            security_passed=True,
        )
    ) == ""


# --------------------------------------------------------------------------
# Advancing and resetting
# --------------------------------------------------------------------------


def test_a_failed_cycle_advances_the_counter() -> None:
    last_result = _security_last_result(test_results=[FAILED_CHECK])

    advance_security_retry_state(
        last_result,
        previous_count=0,
        previous_signature="",
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["security_retry_count"] == 1
    assert last_result["security_repeated_failures"] == 0
    assert last_result["security_failure_signature"]


def test_the_same_failure_twice_records_a_repetition() -> None:
    last_result = _security_last_result(test_results=[FAILED_CHECK])

    signature = build_security_failure_signature(last_result)

    advance_security_retry_state(
        last_result,
        previous_count=1,
        previous_signature=signature,
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["security_repeated_failures"] == 1


def test_a_successful_cycle_resets_the_history() -> None:
    last_result = _security_last_result(
        test_results=[PASSING_CHECK],
        security_passed=True,
        retry_count=2,
        repeated=1,
        signature="stale",
    )

    advance_security_retry_state(
        last_result,
        previous_count=2,
        previous_signature="stale",
        previous_repeated=1,
        cycle_failed=False,
    )

    assert last_result["security_retry_count"] == 0
    assert last_result["security_repeated_failures"] == 0
    assert last_result["security_failure_signature"] == ""

    assert_security_retry_budget(
        {"agents": {"security": {"last_result": last_result}}}
    )


# --------------------------------------------------------------------------
# Persistence and restart
# --------------------------------------------------------------------------


def test_the_budget_survives_save_and_load(tmp_path: Path) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_SECURITY_RETRIES))

    reloaded = load_state(state_path)

    assert get_security_retry_count(reloaded) == MAX_SECURITY_RETRIES

    with pytest.raises(NonConvergingSecurityError):
        assert_security_retry_budget(reloaded)


def test_restarting_the_cli_does_not_reopen_the_budget(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_SECURITY_RETRIES))

    for _ in range(3):
        reloaded = load_state(state_path)

        with pytest.raises(NonConvergingSecurityError):
            assert_security_retry_budget(reloaded)

        save_state(state_path, reloaded)


def test_an_ordinary_retry_does_not_bypass_the_budget() -> None:
    state = retry_agent(
        _state(retry_count=MAX_SECURITY_RETRIES),
        "security",
    )

    assert state["agents"]["security"]["status"] == "READY"

    with pytest.raises(NonConvergingSecurityError):
        assert_security_retry_budget(state)


def test_an_explicit_operator_reset_reopens_the_budget() -> None:
    state = reset_replan_budget(
        _state(retry_count=MAX_SECURITY_RETRIES),
        "security",
        source="cli:retry --reset-replan-budget",
    )

    assert get_security_retry_count(state) == 0
    assert get_security_repeated_failures(state) == 0
    assert get_security_failure_signature(state) == ""
    assert state["agents"]["security"]["status"] == "READY"

    assert_security_retry_budget(state)

    history = state["agents"]["security"]["replan_budget_resets"]

    assert len(history) == 1
    assert history[0]["previous_replan_count"] == MAX_SECURITY_RETRIES


def test_a_reset_preserves_security_diagnostics() -> None:
    state = reset_replan_budget(
        _state(
            retry_count=MAX_SECURITY_RETRIES,
            findings=[{"id": "SEC-1", "severity": "Critical",
                       "status": "OPEN"}],
            blockers=[
                {
                    "message": "The advisory database is unreachable.",
                    "kind": "EXTERNAL_DEPENDENCY",
                    "scope": "EXTERNAL",
                    "fixable_by_agent": False,
                    "requires_human_input": True,
                    "blocking": True,
                }
            ],
        ),
        "security",
    )

    last_result = state["agents"]["security"]["last_result"]

    assert last_result["security_test_results"] == [FAILED_CHECK]
    assert last_result["security_findings"] == [
        {"id": "SEC-1", "severity": "Critical", "status": "OPEN"}
    ]
    assert last_result["security_blockers"]
    assert last_result["security_summary"] == "Security review completed."


def test_a_reset_is_refused_while_budget_remains() -> None:
    with pytest.raises(ReplanBudgetResetError, match="still has"):
        reset_replan_budget(_state(retry_count=0), "security")


# --------------------------------------------------------------------------
# The other budgets are untouched
# --------------------------------------------------------------------------


def test_qa_retry_behaviour_is_unchanged() -> None:
    qa_state = {
        "agents": {
            "qa": {
                "status": "FAILED",
                "last_result": {
                    "qa_retry_count": MAX_QA_RETRIES - 1,
                    "qa_repeated_failures": 0,
                    "qa_failure_signature": "failed_checks|npm test",
                },
            }
        }
    }

    assert_qa_retry_budget(qa_state)

    qa_state["agents"]["qa"]["last_result"][
        "qa_retry_count"
    ] = MAX_QA_RETRIES

    with pytest.raises(ValueError, match="NON_CONVERGING_QA"):
        assert_qa_retry_budget(qa_state)


def test_developer_retry_behaviour_is_unchanged() -> None:
    developer_state = {
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "replan_count": MAX_DEVELOPER_REPLANS - 1,
                    "repeated_failures": 0,
                    "failure_signature": "test_failed|npm test",
                },
            }
        }
    }

    assert_replan_budget(developer_state)

    developer_state["agents"]["developer"]["last_result"][
        "replan_count"
    ] = MAX_DEVELOPER_REPLANS

    with pytest.raises(ValueError, match="not converging"):
        assert_replan_budget(developer_state)


def test_the_three_budgets_are_independent() -> None:
    state = _state(retry_count=MAX_SECURITY_RETRIES)
    state["agents"]["developer"]["last_result"] = {
        "replan_count": 0,
        "repeated_failures": 0,
        "failure_signature": "",
    }
    state["agents"]["qa"]["last_result"] = {
        "qa_retry_count": 0,
        "qa_repeated_failures": 0,
        "qa_failure_signature": "",
    }

    assert_replan_budget(state)
    assert_qa_retry_budget(state)

    with pytest.raises(NonConvergingSecurityError):
        assert_security_retry_budget(state)


# --------------------------------------------------------------------------
# Workflow level
# --------------------------------------------------------------------------


class _CountingSecurityProvider(ModelProvider, SecurityProvider):
    """Always fails Security, and counts every provider call."""

    def __init__(self) -> None:
        self.security_calls = 0
        self.run_calls = 0

    def run(self, context):
        from ai_factory.agent_result import AgentResult

        self.run_calls += 1

        return AgentResult(
            status="COMPLETED",
            summary="Security agent completed.",
        )

    def generate(self, prompt: str) -> str:  # pragma: no cover
        return ""

    def validate_security(self, prompt: str) -> SecurityResult:
        self.security_calls += 1

        return SecurityResult(
            summary="Security review found problems.",
            passed=False,
            findings=[
                SecurityFinding(
                    id="SEC-001",
                    title="Session cookie is not Secure",
                    severity="Critical",
                    affected_component="src/auth/session.ts",
                    description="No Secure attribute.",
                    impact="Session hijacking.",
                    evidence="Set-Cookie header.",
                    recommended_remediation="Set Secure.",
                    priority="P1",
                    status="OPEN",
                )
            ],
            test_commands=["npm audit --audit-level=high"],
        )


def _security_project(root: Path) -> Path:
    state_path = root / ".factory" / "state.yaml"

    state = _state(security_status="READY")
    state["agents"]["security"]["last_result"] = {}
    state["agents"]["qa"]["last_result"] = {
        "qa_passed": True,
        "qa_test_results": [PASSING_CHECK],
    }
    state["agents"]["developer"]["last_result"] = {
        "implemented_files": ["src/auth/session.ts"],
        "implementation_results": [
            {"task_id": "US-001", "summary": "Sessions implemented."}
        ],
    }

    save_state(state_path, state)

    save_state(
        root / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Test Project", "type": "test"},
            "context": {"agents": {"security": []}},
            "ai": {
                "provider": "mock",
                "model": None,
                "settings": {
                    "temperature": None,
                    "max_output_tokens": None,
                },
            },
        },
    )

    return state_path


def _stub_security_commands(monkeypatch) -> None:
    from ai_factory.test_runner import CommandExecutionResult

    monkeypatch.setattr(
        "ai_factory.security_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=1,
            stdout="",
            stderr="vulnerabilities found",
        ),
    )


def test_a_persistently_failing_security_terminates_the_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The loop observed in the previous mission, reproduced and bounded."""

    state_path = _security_project(tmp_path)
    _stub_security_commands(monkeypatch)

    provider = _CountingSecurityProvider()

    with pytest.raises(NonConvergingSecurityError):
        run_workflow(project_root=tmp_path, provider=provider)

    assert provider.security_calls <= MAX_SECURITY_RETRIES

    state = load_state(state_path)

    assert state["agents"]["security"]["status"] == "FAILED"
    assert state["security_gate"]["status"] == "NOT_READY"
    assert state["agents"]["devops"]["status"] == "NOT_STARTED"


def test_no_provider_call_happens_after_exhaustion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _security_project(tmp_path)
    _stub_security_commands(monkeypatch)

    provider = _CountingSecurityProvider()

    with pytest.raises(NonConvergingSecurityError):
        run_workflow(project_root=tmp_path, provider=provider)

    spent = provider.security_calls
    state_before = load_state(state_path)

    with pytest.raises(NonConvergingSecurityError):
        run_next_agent(project_root=tmp_path, provider=provider)

    assert provider.security_calls == spent
    assert provider.run_calls == spent

    assert load_state(state_path) == state_before


def test_diagnostics_survive_the_bounded_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _security_project(tmp_path)
    _stub_security_commands(monkeypatch)

    with pytest.raises(NonConvergingSecurityError):
        run_workflow(
            project_root=tmp_path,
            provider=_CountingSecurityProvider(),
        )

    last_result = load_state(state_path)["agents"]["security"][
        "last_result"
    ]

    assert last_result["security_test_results"]
    assert last_result["security_test_results"][0]["passed"] is False
    assert last_result["security_findings"][0]["id"] == "SEC-001"
    assert last_result["security_findings"][0]["severity"] == "Critical"
    assert last_result["security_summary"] == (
        "Security review found problems."
    )
    assert last_result["security_model_passed"] is False
    assert last_result["security_passed"] is False
    assert last_result["security_retry_count"] >= 1
    assert last_result["security_failure_signature"]
