"""SRE may retry. It may not retry forever.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. Developer, QA, Security and
DevOps are bounded; SRE was not. Making SRE fail closed when objective
evidence is missing turned that from a latent defect into an observable
hang: `sre == FAILED` selected SRE again, called the provider again, failed
again, without limit.

SRE is bounded for a reason established by audit rather than by analogy.
`SREResult` declares `summary`, `passed`, `findings`, `test_commands`,
`blockers`, `observability_ready` and `incident_readiness` - and nothing
else. It carries no file changes at all, not even the unapplied `changes[]`
DevOps declares. A repeated SRE cycle therefore evaluates the identical
governed product and operational state with an identical prompt.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from ai_factory.devops_retry_guard import (
    MAX_DEVOPS_RETRIES,
    assert_devops_retry_budget,
)
from ai_factory.production_gate import evaluate_production_gate
from ai_factory.project import initialize_project
from ai_factory.providers import ModelProvider, SREProvider
from ai_factory.qa_retry_guard import (
    MAX_QA_RETRIES,
    assert_qa_retry_budget,
)
from ai_factory.replan_guard import (
    BUDGETED_AGENTS,
    MAX_DEVELOPER_REPLANS,
    ReplanBudgetResetError,
    assert_replan_budget,
    budget_limit,
    is_budget_exhausted,
    reset_replan_budget,
)
from ai_factory.runtime import run_next_agent, run_workflow
from ai_factory.security_retry_guard import (
    MAX_SECURITY_RETRIES,
    assert_security_retry_budget,
)
from ai_factory.sre_result import SREFinding, SREResult
from ai_factory.sre_retry_guard import (
    MAX_SRE_RETRIES,
    NonConvergingSREError,
    advance_sre_retry_state,
    assert_sre_retry_budget,
    build_sre_failure_signature,
    get_sre_failure_signature,
    get_sre_repeated_failures,
    get_sre_retry_count,
    is_sre_budget_exhausted,
)
from ai_factory.state import load_state, save_state
from ai_factory.transitions import retry_agent


FAILED_CHECK = {
    "command": "python -m pytest tests/test_smoke.py -q",
    "returncode": 1,
    "passed": False,
    "stdout": "",
    "stderr": "smoke check failed",
}

PASSING_CHECK = {
    "command": "python -m pytest tests/test_smoke.py -q",
    "returncode": 0,
    "passed": True,
    "stdout": "",
    "stderr": "",
}

OPEN_HIGH_FINDING = {
    "id": "SRE-001",
    "title": "No alert on error rate.",
    "severity": "High",
    "category": "observability",
    "description": "The service exposes no error-rate alert.",
    "recommendation": "Add an alert rule on the 5xx ratio.",
    "status": "OPEN",
}

EXTERNAL_BLOCKER = {
    "message": "The metrics backend is unreachable.",
    "kind": "EXTERNAL_DEPENDENCY",
    "scope": "EXTERNAL",
    "fixable_by_agent": False,
    "requires_human_input": True,
    "blocking": True,
}


def _sre_last_result(
    retry_count: int = 0,
    repeated: int = 0,
    signature: str = "",
    test_results: list[dict] | None = None,
    blockers: list[dict] | None = None,
    findings: list[dict] | None = None,
    observability_ready: bool = True,
    incident_readiness: bool = True,
    sre_passed: bool = False,
    summary: str = "Operational validation completed.",
) -> dict:
    return {
        "sre_summary": summary,
        "sre_model_passed": sre_passed,
        "sre_passed": sre_passed,
        "sre_test_results": (
            test_results if test_results is not None else [FAILED_CHECK]
        ),
        "sre_findings": findings if findings is not None else [],
        "sre_blockers": blockers or [],
        "observability_ready": observability_ready,
        "incident_readiness": incident_readiness,
        "sre_retry_count": retry_count,
        "sre_repeated_failures": repeated,
        "sre_failure_signature": signature,
    }


def _state(sre_status: str = "FAILED", **kwargs) -> dict:
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
                "status": sre_status,
                "last_result": _sre_last_result(**kwargs),
            },
        },
        "sre_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
        "production_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
    }


# --------------------------------------------------------------------------
# The bound
# --------------------------------------------------------------------------


def test_a_first_sre_failure_may_be_retried() -> None:
    assert_sre_retry_budget(_state(retry_count=1))


def test_the_bound_is_finite_and_conservative() -> None:
    assert MAX_SRE_RETRIES == 2
    assert MAX_SRE_RETRIES < MAX_DEVELOPER_REPLANS


def test_persistent_sre_failure_cannot_loop_forever() -> None:
    with pytest.raises(
        NonConvergingSREError,
        match="NON_CONVERGING_SRE",
    ):
        assert_sre_retry_budget(_state(retry_count=MAX_SRE_RETRIES))


def test_an_identical_repeated_failure_stops_earlier() -> None:
    with pytest.raises(NonConvergingSREError):
        assert_sre_retry_budget(_state(retry_count=1, repeated=1))


def test_the_guard_reads_only_persisted_counters() -> None:
    assert_sre_retry_budget(_state(retry_count=0, repeated=0))
    assert_sre_retry_budget(_state(retry_count=1, repeated=0))


def test_exhaustion_is_reported_through_the_shared_predicate() -> None:
    exhausted = _state(retry_count=MAX_SRE_RETRIES)

    assert is_sre_budget_exhausted(exhausted) is True
    assert is_budget_exhausted(exhausted, "sre") is True

    remaining = _state(retry_count=1)

    assert is_sre_budget_exhausted(remaining) is False
    assert is_budget_exhausted(remaining, "sre") is False


def test_sre_joins_the_shared_budget_registry() -> None:
    assert "sre" in BUDGETED_AGENTS
    assert budget_limit("sre") == MAX_SRE_RETRIES


# --------------------------------------------------------------------------
# Structured signature only
# --------------------------------------------------------------------------


def test_the_signature_uses_failed_commands_and_engine_reasons() -> None:
    signature = build_sre_failure_signature(
        _sre_last_result(test_results=[FAILED_CHECK])
    )

    assert "failed_checks" in signature
    assert FAILED_CHECK["command"] in signature


def test_the_signature_ignores_summary_prose() -> None:
    first = _sre_last_result(
        test_results=[FAILED_CHECK],
        summary="The smoke check times out against the staging cluster.",
    )

    second = _sre_last_result(
        test_results=[FAILED_CHECK],
        summary="An entirely different narrative about the same run.",
    )

    assert build_sre_failure_signature(first) == (
        build_sre_failure_signature(second)
    )


def test_the_signature_ignores_finding_prose_and_identifiers() -> None:
    """Only the count of blocking findings participates, never its wording."""

    renamed = dict(OPEN_HIGH_FINDING)
    renamed["id"] = "SRE-047"
    renamed["title"] = "Completely different title."
    renamed["description"] = "Completely different description."
    renamed["recommendation"] = "Completely different remediation."
    renamed["category"] = "resilience"

    assert build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            findings=[OPEN_HIGH_FINDING],
        )
    ) == build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            findings=[renamed],
        )
    )


def test_the_signature_ignores_blocker_message_prose() -> None:
    other = dict(EXTERNAL_BLOCKER)
    other["message"] = "A different sentence about the same outage."

    assert build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            blockers=[EXTERNAL_BLOCKER],
        )
    ) == build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            blockers=[other],
        )
    )


def test_no_natural_language_heuristic_is_introduced() -> None:
    """The signature never reads prose, so prose can never change it.

    Every free-form field is replaced at once. If any of them reached the
    signature - by substring, by similarity, by any wording heuristic - the
    two signatures would differ.
    """

    baseline = _sre_last_result(
        test_results=[FAILED_CHECK],
        findings=[OPEN_HIGH_FINDING],
        blockers=[EXTERNAL_BLOCKER],
    )

    prose_rewritten = _sre_last_result(
        test_results=[FAILED_CHECK],
        findings=[
            {
                **OPEN_HIGH_FINDING,
                "id": "X",
                "title": "Zzz",
                "category": "Zzz",
                "description": "Zzz",
                "recommendation": "Zzz",
            }
        ],
        blockers=[{**EXTERNAL_BLOCKER, "message": "Zzz"}],
        summary="Zzz",
    )

    signature = build_sre_failure_signature(baseline)

    assert signature == build_sre_failure_signature(prose_rewritten)

    # The failing command is the one string that legitimately survives: it
    # is what the engine executed, not what the agent wrote about it.
    assert FAILED_CHECK["command"] in signature

    for prose in (
        "Zzz",
        "timeout",
        "alert",
        OPEN_HIGH_FINDING["id"],
        OPEN_HIGH_FINDING["title"],
        OPEN_HIGH_FINDING["category"],
        OPEN_HIGH_FINDING["description"],
        OPEN_HIGH_FINDING["recommendation"],
        EXTERNAL_BLOCKER["message"],
        baseline["sre_summary"],
    ):
        assert prose not in signature


def test_missing_evidence_has_its_own_structural_signature() -> None:
    assert "no_evidence" in build_sre_failure_signature(
        _sre_last_result(test_results=[])
    )


def test_an_undeclared_observability_flag_changes_the_signature() -> None:
    signature = build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            observability_ready=False,
        )
    )

    assert "observability_not_ready" in signature


def test_an_undeclared_incident_readiness_changes_the_signature() -> None:
    signature = build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            incident_readiness=False,
        )
    )

    assert "incident_readiness_not_ready" in signature


def test_blocking_findings_participate_only_as_a_count() -> None:
    signature = build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            findings=[OPEN_HIGH_FINDING],
        )
    )

    assert "unresolved_findings:1" in signature


def test_a_resolved_finding_is_not_counted() -> None:
    resolved = dict(OPEN_HIGH_FINDING)
    resolved["status"] = "RESOLVED"

    assert "unresolved_findings" not in build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            findings=[resolved],
        )
    )


def test_blocking_blockers_participate_only_as_a_count() -> None:
    signature = build_sre_failure_signature(
        _sre_last_result(
            test_results=[FAILED_CHECK],
            blockers=[EXTERNAL_BLOCKER],
        )
    )

    assert "blocking_blockers:1" in signature


def test_a_model_reported_failure_is_recorded() -> None:
    signature = build_sre_failure_signature(
        _sre_last_result(
            test_results=[PASSING_CHECK],
            sre_passed=False,
        )
    )

    assert "model_reported_failure" in signature


def test_a_different_failing_command_is_a_different_signature() -> None:
    other = dict(FAILED_CHECK)
    other["command"] = "python -m pytest tests/test_runbook.py -q"

    assert build_sre_failure_signature(
        _sre_last_result(test_results=[FAILED_CHECK])
    ) != build_sre_failure_signature(
        _sre_last_result(test_results=[other])
    )


def test_a_successful_cycle_has_no_signature() -> None:
    assert build_sre_failure_signature(
        _sre_last_result(
            test_results=[PASSING_CHECK],
            sre_passed=True,
        )
    ) == ""


# --------------------------------------------------------------------------
# Advancing and resetting
# --------------------------------------------------------------------------


def test_a_failed_cycle_advances_the_counter() -> None:
    last_result = _sre_last_result(test_results=[FAILED_CHECK])

    advance_sre_retry_state(
        last_result,
        previous_count=0,
        previous_signature="",
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["sre_retry_count"] == 1
    assert last_result["sre_repeated_failures"] == 0
    assert last_result["sre_failure_signature"]


def test_the_same_failure_twice_records_a_repetition() -> None:
    last_result = _sre_last_result(test_results=[FAILED_CHECK])

    signature = build_sre_failure_signature(last_result)

    advance_sre_retry_state(
        last_result,
        previous_count=1,
        previous_signature=signature,
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["sre_repeated_failures"] == 1


def test_a_successful_sre_resets_the_retry_history() -> None:
    last_result = _sre_last_result(
        test_results=[PASSING_CHECK],
        sre_passed=True,
        retry_count=2,
        repeated=1,
        signature="stale",
    )

    advance_sre_retry_state(
        last_result,
        previous_count=2,
        previous_signature="stale",
        previous_repeated=1,
        cycle_failed=False,
    )

    assert last_result["sre_retry_count"] == 0
    assert last_result["sre_repeated_failures"] == 0
    assert last_result["sre_failure_signature"] == ""

    assert_sre_retry_budget(
        {"agents": {"sre": {"last_result": last_result}}}
    )


# --------------------------------------------------------------------------
# Persistence and restart
# --------------------------------------------------------------------------


def test_the_budget_survives_save_and_load(tmp_path: Path) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(
        state_path,
        _state(
            retry_count=MAX_SRE_RETRIES,
            repeated=1,
            signature="failed_checks|observability_not_ready",
        ),
    )

    reloaded = load_state(state_path)

    assert get_sre_retry_count(reloaded) == MAX_SRE_RETRIES
    assert get_sre_repeated_failures(reloaded) == 1
    assert get_sre_failure_signature(reloaded) == (
        "failed_checks|observability_not_ready"
    )

    with pytest.raises(NonConvergingSREError):
        assert_sre_retry_budget(reloaded)


def test_restarting_the_cli_does_not_reopen_the_budget(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_SRE_RETRIES))

    for _ in range(3):
        reloaded = load_state(state_path)

        with pytest.raises(NonConvergingSREError):
            assert_sre_retry_budget(reloaded)

        save_state(state_path, reloaded)


def test_an_ordinary_retry_does_not_bypass_the_budget() -> None:
    state = retry_agent(
        _state(retry_count=MAX_SRE_RETRIES),
        "sre",
    )

    assert state["agents"]["sre"]["status"] == "READY"

    with pytest.raises(NonConvergingSREError):
        assert_sre_retry_budget(state)


def test_an_explicit_operator_reset_reopens_the_budget() -> None:
    state = reset_replan_budget(
        _state(retry_count=MAX_SRE_RETRIES),
        "sre",
        source="cli:retry --reset-replan-budget",
    )

    assert get_sre_retry_count(state) == 0
    assert get_sre_repeated_failures(state) == 0
    assert get_sre_failure_signature(state) == ""
    assert state["agents"]["sre"]["status"] == "READY"

    assert_sre_retry_budget(state)

    history = state["agents"]["sre"]["replan_budget_resets"]

    assert len(history) == 1
    assert history[0]["previous_replan_count"] == MAX_SRE_RETRIES
    assert history[0]["source"] == "cli:retry --reset-replan-budget"


def test_a_reset_preserves_sre_diagnostics() -> None:
    state = reset_replan_budget(
        _state(
            retry_count=MAX_SRE_RETRIES,
            findings=[OPEN_HIGH_FINDING],
            blockers=[EXTERNAL_BLOCKER],
            observability_ready=False,
            incident_readiness=False,
        ),
        "sre",
    )

    last_result = state["agents"]["sre"]["last_result"]

    assert last_result["sre_test_results"] == [FAILED_CHECK]
    assert last_result["sre_findings"] == [OPEN_HIGH_FINDING]
    assert last_result["sre_blockers"] == [EXTERNAL_BLOCKER]
    assert last_result["observability_ready"] is False
    assert last_result["incident_readiness"] is False
    assert last_result["sre_summary"] == (
        "Operational validation completed."
    )


def test_a_reset_is_refused_while_budget_remains() -> None:
    with pytest.raises(ReplanBudgetResetError, match="still has"):
        reset_replan_budget(_state(retry_count=0), "sre")


def test_a_reset_is_refused_unless_sre_failed() -> None:
    with pytest.raises(ReplanBudgetResetError, match="must be FAILED"):
        reset_replan_budget(
            _state(
                sre_status="REVIEW_REQUIRED",
                retry_count=MAX_SRE_RETRIES,
            ),
            "sre",
        )


def test_a_reset_makes_no_provider_call() -> None:
    """`reset_replan_budget` takes state only - there is nothing to call."""

    provider = _CountingSREProvider()

    reset_replan_budget(_state(retry_count=MAX_SRE_RETRIES), "sre")

    assert provider.sre_calls == 0
    assert provider.run_calls == 0


# --------------------------------------------------------------------------
# The other budgets are untouched
# --------------------------------------------------------------------------


def test_the_other_budgets_are_unchanged() -> None:
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

    with pytest.raises(ValueError, match="NON_CONVERGING_QA"):
        assert_qa_retry_budget(
            {
                "agents": {
                    "qa": {
                        "last_result": {
                            "qa_retry_count": MAX_QA_RETRIES,
                        }
                    }
                }
            }
        )

    with pytest.raises(ValueError, match="NON_CONVERGING_SECURITY"):
        assert_security_retry_budget(
            {
                "agents": {
                    "security": {
                        "last_result": {
                            "security_retry_count": MAX_SECURITY_RETRIES,
                        }
                    }
                }
            }
        )

    with pytest.raises(ValueError, match="NON_CONVERGING_DEVOPS"):
        assert_devops_retry_budget(
            {
                "agents": {
                    "devops": {
                        "last_result": {
                            "devops_retry_count": MAX_DEVOPS_RETRIES,
                        }
                    }
                }
            }
        )


def test_the_five_budgets_are_independent() -> None:
    state = _state(retry_count=MAX_SRE_RETRIES)
    state["agents"]["developer"]["last_result"] = {"replan_count": 0}
    state["agents"]["qa"]["last_result"] = {"qa_retry_count": 0}
    state["agents"]["security"]["last_result"] = {
        "security_retry_count": 0
    }
    state["agents"]["devops"]["last_result"] = {"devops_retry_count": 0}

    assert_replan_budget(state)
    assert_qa_retry_budget(state)
    assert_security_retry_budget(state)
    assert_devops_retry_budget(state)

    with pytest.raises(NonConvergingSREError):
        assert_sre_retry_budget(state)


# --------------------------------------------------------------------------
# Orchestration audit
# --------------------------------------------------------------------------


def test_every_agent_that_can_fail_autonomously_is_now_budgeted() -> None:
    """The audit, as an assertion rather than a claim.

    Only `BLOCKED` and `REVIEW_REQUIRED` are reachable from an
    `AgentResult`, and both stop `get_next_agent`. `FAILED` - the status
    that makes an agent be re-selected - is written by the runtime for
    exactly the five validation agents, and all five are budgeted.
    """

    from ai_factory.orchestrator import AGENT_ORDER, get_next_agent
    from ai_factory.result_policy import RESULT_STATUS_TO_AGENT_STATUS

    assert set(RESULT_STATUS_TO_AGENT_STATUS.values()) == {
        "BLOCKED",
        "REVIEW_REQUIRED",
    }

    assert BUDGETED_AGENTS == {
        "developer",
        "qa",
        "security",
        "devops",
        "sre",
    }

    assert AGENT_ORDER[-1] == "sre"

    for agent_name in ("product", "ux_ui", "architect"):
        state = {
            "agents": {
                name: {"status": "APPROVED"} for name in AGENT_ORDER
            }
        }

        state["agents"][agent_name]["status"] = "REVIEW_REQUIRED"

        assert get_next_agent(state) is None


def test_an_unbudgeted_agent_cannot_have_a_budget_reopened() -> None:
    for agent_name in ("product", "ux_ui", "architect"):
        with pytest.raises(
            ReplanBudgetResetError,
            match="no replanning budget",
        ):
            reset_replan_budget(
                {
                    "agents": {
                        agent_name: {
                            "status": "FAILED",
                            "last_result": {},
                        }
                    }
                },
                agent_name,
            )


# --------------------------------------------------------------------------
# Workflow level
# --------------------------------------------------------------------------


class _CountingSREProvider(ModelProvider, SREProvider):
    """Always fails SRE, and counts every provider call."""

    def __init__(
        self,
        result: SREResult | None = None,
    ) -> None:
        self.sre_calls = 0
        self.run_calls = 0
        self._result = result

    def run(self, context):
        from ai_factory.agent_result import AgentResult

        self.run_calls += 1

        return AgentResult(
            status="COMPLETED",
            summary="SRE agent completed.",
        )

    def generate(self, prompt: str) -> str:  # pragma: no cover
        return ""

    def validate_sre(self, prompt: str) -> SREResult:
        self.sre_calls += 1

        if self._result is not None:
            return self._result

        return SREResult(
            summary="The operational smoke check does not pass.",
            passed=False,
            findings=[
                SREFinding(
                    id="SRE-001",
                    title="No alert on error rate.",
                    severity="High",
                    category="observability",
                    description="The service exposes no error-rate alert.",
                    recommendation="Add an alert rule on the 5xx ratio.",
                    status="OPEN",
                )
            ],
            test_commands=["python -m pytest tests/test_smoke.py -q"],
            blockers=[],
            observability_ready=True,
            incident_readiness=True,
        )


def _sre_project(root: Path) -> Path:
    state_path = root / ".factory" / "state.yaml"

    state = _state(sre_status="READY")
    state["agents"]["sre"]["last_result"] = {}
    state["agents"]["developer"]["last_result"] = {
        "implemented_files": ["src/app.ts"],
        "implementation_results": [
            {"task_id": "US-001", "summary": "App implemented."}
        ],
    }
    state["agents"]["qa"]["last_result"] = {"qa_passed": True}
    state["agents"]["security"]["last_result"] = {
        "security_passed": True,
    }
    state["agents"]["devops"]["last_result"] = {
        "devops_passed": True,
        "deployment_ready": True,
    }

    save_state(state_path, state)

    save_state(
        root / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Test Project", "type": "test"},
            "context": {"agents": {"sre": []}},
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


def _stub_sre_commands(monkeypatch, passed: bool = False) -> None:
    from ai_factory.test_runner import CommandExecutionResult

    monkeypatch.setattr(
        "ai_factory.sre_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=0 if passed else 1,
            stdout="",
            stderr="" if passed else "smoke check failed",
        ),
    )


def test_a_persistently_failing_sre_terminates_the_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The unbounded loop, reproduced and bounded."""

    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    provider = _CountingSREProvider()

    with pytest.raises(NonConvergingSREError):
        run_workflow(project_root=tmp_path, provider=provider)

    assert provider.sre_calls <= MAX_SRE_RETRIES

    state = load_state(state_path)

    assert state["agents"]["sre"]["status"] == "FAILED"


def test_the_sre_gate_stays_not_ready_after_a_bounded_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    with pytest.raises(NonConvergingSREError):
        run_workflow(
            project_root=tmp_path,
            provider=_CountingSREProvider(),
        )

    state = load_state(state_path)

    assert state["sre_gate"]["status"] == "NOT_READY"
    assert state["sre_gate"]["human_approval"] is False
    assert state["sre_gate"]["reasons"]


def test_the_production_gate_stays_not_ready_after_a_bounded_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    with pytest.raises(NonConvergingSREError):
        run_workflow(
            project_root=tmp_path,
            provider=_CountingSREProvider(),
        )

    state = load_state(state_path)

    assert state["production_gate"]["status"] == "NOT_READY"
    assert state["production_gate"]["human_approval"] is False
    assert state["approvals"]["production_deployment"] is False

    evaluation = evaluate_production_gate(state)

    assert evaluation.ready is False
    assert "SRE is not approved." in evaluation.reasons


def test_no_provider_call_happens_after_exhaustion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    provider = _CountingSREProvider()

    with pytest.raises(NonConvergingSREError):
        run_workflow(project_root=tmp_path, provider=provider)

    spent = provider.sre_calls
    runs = provider.run_calls

    with pytest.raises(NonConvergingSREError):
        run_next_agent(project_root=tmp_path, provider=provider)

    assert provider.sre_calls == spent
    assert provider.run_calls == runs


def test_the_state_is_byte_identical_when_the_guard_refuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    provider = _CountingSREProvider()

    with pytest.raises(NonConvergingSREError):
        run_workflow(project_root=tmp_path, provider=provider)

    before = state_path.read_bytes()

    for _ in range(5):
        with pytest.raises(NonConvergingSREError):
            run_next_agent(project_root=tmp_path, provider=provider)

    assert state_path.read_bytes() == before


def test_the_hard_bound_rejects_before_provider_invocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The refusal costs nothing: no agent run, no SRE validation."""

    _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    exhausted = load_state(tmp_path / ".factory" / "state.yaml")
    exhausted["agents"]["sre"]["status"] = "FAILED"
    exhausted["agents"]["sre"]["last_result"] = _sre_last_result(
        retry_count=MAX_SRE_RETRIES,
    )

    save_state(tmp_path / ".factory" / "state.yaml", exhausted)

    provider = _CountingSREProvider()

    with pytest.raises(NonConvergingSREError):
        run_next_agent(project_root=tmp_path, provider=provider)

    assert provider.run_calls == 0
    assert provider.sre_calls == 0


def test_diagnostics_survive_the_bounded_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    with pytest.raises(NonConvergingSREError):
        run_workflow(
            project_root=tmp_path,
            provider=_CountingSREProvider(),
        )

    last_result = load_state(state_path)["agents"]["sre"]["last_result"]

    assert last_result["sre_test_results"]
    assert last_result["sre_test_results"][0]["passed"] is False

    assert last_result["sre_findings"]
    assert last_result["sre_findings"][0]["id"] == "SRE-001"
    assert last_result["sre_findings"][0]["severity"] == "High"

    assert last_result["observability_ready"] is True
    assert last_result["incident_readiness"] is True

    assert last_result["sre_summary"] == (
        "The operational smoke check does not pass."
    )
    assert last_result["sre_model_passed"] is False
    assert last_result["sre_passed"] is False

    assert last_result["sre_retry_count"] >= 1
    assert last_result["sre_failure_signature"]


def test_blockers_survive_the_bounded_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    provider = _CountingSREProvider(
        result=SREResult(
            summary="The metrics backend is unreachable.",
            passed=False,
            findings=[],
            test_commands=["python -m pytest tests/test_smoke.py -q"],
            blockers=[EXTERNAL_BLOCKER],
            observability_ready=False,
            incident_readiness=False,
        )
    )

    run_workflow(project_root=tmp_path, provider=provider)

    state = load_state(state_path)
    last_result = state["agents"]["sre"]["last_result"]

    assert state["agents"]["sre"]["status"] == "BLOCKED"
    assert last_result["sre_blockers"]
    assert last_result["observability_ready"] is False
    assert last_result["incident_readiness"] is False
    assert last_result["sre_retry_count"] >= 1
    assert state["sre_gate"]["status"] == "NOT_READY"


def test_the_thousand_iteration_sre_loop_terminates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The reproduction, bounded.

    Driving `run_next_agent` a thousand times used to mean a thousand
    provider calls. It now stops deterministically, and the number of SRE
    provider calls is capped by the budget rather than by the loop.
    """

    _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    provider = _CountingSREProvider()

    iterations = 0

    with pytest.raises(NonConvergingSREError):
        for _ in range(1000):
            iterations += 1
            run_next_agent(project_root=tmp_path, provider=provider)

    assert iterations <= MAX_SRE_RETRIES + 1
    assert provider.sre_calls <= MAX_SRE_RETRIES
    assert provider.run_calls <= MAX_SRE_RETRIES


def test_an_explicit_reset_reopens_exactly_one_more_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    provider = _CountingSREProvider()

    with pytest.raises(NonConvergingSREError):
        run_workflow(project_root=tmp_path, provider=provider)

    spent = provider.sre_calls

    state = reset_replan_budget(
        load_state(state_path),
        "sre",
        source="cli:retry --reset-replan-budget",
    )

    save_state(state_path, state)

    with pytest.raises(NonConvergingSREError):
        run_workflow(project_root=tmp_path, provider=provider)

    assert provider.sre_calls <= spent + MAX_SRE_RETRIES

    reopened = load_state(state_path)

    assert reopened["agents"]["sre"]["status"] == "FAILED"
    assert reopened["sre_gate"]["status"] == "NOT_READY"
    assert reopened["agents"]["sre"]["replan_budget_resets"]


def test_the_normal_successful_sre_path_is_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch, passed=True)

    provider = _CountingSREProvider(
        result=SREResult(
            summary="Operational readiness confirmed.",
            passed=True,
            findings=[],
            test_commands=["python -m pytest tests/test_smoke.py -q"],
            blockers=[],
            observability_ready=True,
            incident_readiness=True,
        )
    )

    run_workflow(project_root=tmp_path, provider=provider)

    state = load_state(state_path)
    last_result = state["agents"]["sre"]["last_result"]

    assert state["agents"]["sre"]["status"] == "REVIEW_REQUIRED"
    assert state["sre_gate"]["status"] == "READY_FOR_REVIEW"
    assert last_result["sre_passed"] is True

    assert last_result["sre_retry_count"] == 0
    assert last_result["sre_repeated_failures"] == 0
    assert last_result["sre_failure_signature"] == ""

    assert provider.sre_calls == 1


# --------------------------------------------------------------------------
# The operator's explicit recovery, through the CLI
# --------------------------------------------------------------------------


def _cli_project(tmp_path: Path) -> Path:
    project_root = initialize_project("SRE Reset Probe", tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    state = load_state(state_path)
    seeded = _state(retry_count=MAX_SRE_RETRIES)

    state["agents"] = seeded["agents"]
    state["approvals"] = seeded["approvals"]
    state["sre_gate"] = seeded["sre_gate"]
    state["project"]["phase"] = "sre"

    save_state(state_path, state)

    return project_root


def _run_cli(project_root: Path, *arguments: str):
    return subprocess.run(
        [sys.executable, "-m", "ai_factory.cli", *arguments],
        cwd=project_root,
        capture_output=True,
        text=True,
    )


def test_the_cli_reopens_the_sre_budget_and_reports_its_own_limit(
    tmp_path: Path,
) -> None:
    project_root = _cli_project(tmp_path)

    completed = _run_cli(
        project_root,
        "retry",
        "sre",
        "--reset-replan-budget",
    )

    output = completed.stdout + completed.stderr

    assert completed.returncode == 0, output
    assert "replanning budget" in output.lower()
    assert "was opened" in output.lower()
    assert "diagnostics" in output.lower()
    assert f"limit {MAX_SRE_RETRIES}" in output
    assert f"{MAX_SRE_RETRIES} previous cycles cleared" in output

    state = load_state(project_root / ".factory" / "state.yaml")

    assert get_sre_retry_count(state) == 0
    assert state["agents"]["sre"]["status"] == "READY"
    assert state["agents"]["sre"]["replan_budget_resets"]


def test_the_plain_cli_retry_does_not_reopen_the_sre_budget(
    tmp_path: Path,
) -> None:
    project_root = _cli_project(tmp_path)

    completed = _run_cli(project_root, "retry", "sre")

    assert completed.returncode == 0, completed.stdout + completed.stderr

    state = load_state(project_root / ".factory" / "state.yaml")

    assert state["agents"]["sre"]["status"] == "READY"
    assert get_sre_retry_count(state) == MAX_SRE_RETRIES

    with pytest.raises(NonConvergingSREError):
        assert_sre_retry_budget(state)


def test_the_cli_still_reports_the_developer_limit_for_the_developer(
    tmp_path: Path,
) -> None:
    """The shared message must not have been retargeted to SRE."""

    project_root = _cli_project(tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    state = load_state(state_path)
    state["agents"]["developer"] = {
        "status": "FAILED",
        "last_result": {
            "replan_count": MAX_DEVELOPER_REPLANS,
            "repeated_failures": 0,
            "failure_signature": "test_failed|npm test",
        },
    }

    save_state(state_path, state)

    completed = _run_cli(
        project_root,
        "retry",
        "developer",
        "--reset-replan-budget",
    )

    output = completed.stdout + completed.stderr

    assert completed.returncode == 0, output
    assert f"limit {MAX_DEVELOPER_REPLANS}" in output


def test_a_success_after_a_failure_clears_the_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A later independent SRE phase never inherits stale non-convergence."""

    state_path = _sre_project(tmp_path)
    _stub_sre_commands(monkeypatch)

    failing = _CountingSREProvider()

    with pytest.raises(NonConvergingSREError):
        run_workflow(project_root=tmp_path, provider=failing)

    assert get_sre_retry_count(load_state(state_path)) >= 1

    state = reset_replan_budget(
        load_state(state_path),
        "sre",
        source="cli:retry --reset-replan-budget",
    )

    save_state(state_path, state)

    _stub_sre_commands(monkeypatch, passed=True)

    passing = _CountingSREProvider(
        result=SREResult(
            summary="Operational readiness confirmed.",
            passed=True,
            findings=[],
            test_commands=["python -m pytest tests/test_smoke.py -q"],
            blockers=[],
            observability_ready=True,
            incident_readiness=True,
        )
    )

    run_workflow(project_root=tmp_path, provider=passing)

    last_result = load_state(state_path)["agents"]["sre"]["last_result"]

    assert last_result["sre_retry_count"] == 0
    assert last_result["sre_repeated_failures"] == 0
    assert last_result["sre_failure_signature"] == ""
