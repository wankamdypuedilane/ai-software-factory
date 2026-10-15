"""DevOps may retry. It may not retry forever.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. Developer, QA and Security are
bounded; DevOps was not. Requiring objective evidence for DevOps success made
that observable: with the mock declaring no checks, DevOps began to fail and
the loop had nothing to stop it.

DevOps is bounded for a reason established by audit rather than by analogy:
`changes[]` are recorded but never applied to the workspace, so a repeated
DevOps cycle inspects a governed state that DevOps itself never altered.
"""

from pathlib import Path

import pytest

from ai_factory.devops_result import DevOpsResult
from ai_factory.devops_retry_guard import (
    MAX_DEVOPS_RETRIES,
    NonConvergingDevOpsError,
    advance_devops_retry_state,
    assert_devops_retry_budget,
    build_devops_failure_signature,
    get_devops_failure_signature,
    get_devops_repeated_failures,
    get_devops_retry_count,
)
from ai_factory.providers import DevOpsProvider, ModelProvider
from ai_factory.qa_retry_guard import MAX_QA_RETRIES, assert_qa_retry_budget
from ai_factory.replan_guard import (
    MAX_DEVELOPER_REPLANS,
    ReplanBudgetResetError,
    assert_replan_budget,
    reset_replan_budget,
)
from ai_factory.runtime import run_next_agent, run_workflow
from ai_factory.security_retry_guard import (
    MAX_SECURITY_RETRIES,
    assert_security_retry_budget,
)
from ai_factory.state import load_state, save_state
from ai_factory.transitions import retry_agent


ROLLBACK = "Redeploy the previous image tag."

FAILED_CHECK = {
    "command": "npm run build",
    "returncode": 1,
    "passed": False,
    "stdout": "",
    "stderr": "build failed",
}

PASSING_CHECK = {
    "command": "npm run build",
    "returncode": 0,
    "passed": True,
    "stdout": "",
    "stderr": "",
}


def _devops_last_result(
    retry_count: int = 0,
    repeated: int = 0,
    signature: str = "",
    test_results: list[dict] | None = None,
    blockers: list[dict] | None = None,
    deployment_ready: bool = True,
    rollback_strategy: str = ROLLBACK,
    devops_passed: bool = False,
) -> dict:
    return {
        "devops_summary": "Deployment pipeline prepared.",
        "devops_model_passed": devops_passed,
        "devops_passed": devops_passed,
        "devops_test_results": (
            test_results if test_results is not None else [FAILED_CHECK]
        ),
        "devops_changes": [],
        "devops_blockers": blockers or [],
        "deployment_ready": deployment_ready,
        "rollback_strategy": rollback_strategy,
        "devops_retry_count": retry_count,
        "devops_repeated_failures": repeated,
        "devops_failure_signature": signature,
    }


def _state(devops_status: str = "FAILED", **kwargs) -> dict:
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
                "status": devops_status,
                "last_result": _devops_last_result(**kwargs),
            },
            "sre": {"status": "NOT_STARTED"},
        },
        "devops_gate": {
            "status": "NOT_READY",
            "reasons": [],
            "human_approval": False,
        },
    }


# --------------------------------------------------------------------------
# The bound
# --------------------------------------------------------------------------


def test_a_first_devops_failure_may_be_retried() -> None:
    assert_devops_retry_budget(_state(retry_count=1))


def test_the_bound_is_finite_and_conservative() -> None:
    assert MAX_DEVOPS_RETRIES == 2
    assert MAX_DEVOPS_RETRIES < MAX_DEVELOPER_REPLANS


def test_persistent_devops_failure_cannot_loop_forever() -> None:
    with pytest.raises(
        NonConvergingDevOpsError,
        match="NON_CONVERGING_DEVOPS",
    ):
        assert_devops_retry_budget(
            _state(retry_count=MAX_DEVOPS_RETRIES)
        )


def test_an_identical_repeated_failure_stops_earlier() -> None:
    with pytest.raises(NonConvergingDevOpsError):
        assert_devops_retry_budget(_state(retry_count=1, repeated=1))


def test_the_guard_reads_only_persisted_counters() -> None:
    assert_devops_retry_budget(_state(retry_count=0, repeated=0))
    assert_devops_retry_budget(_state(retry_count=1, repeated=0))


# --------------------------------------------------------------------------
# Structured signature only
# --------------------------------------------------------------------------


def test_the_signature_uses_failed_commands_and_engine_reasons() -> None:
    signature = build_devops_failure_signature(
        _devops_last_result(test_results=[FAILED_CHECK])
    )

    assert "failed_checks" in signature
    assert "npm run build" in signature


def test_the_signature_ignores_prose_and_change_descriptions() -> None:
    first = _devops_last_result(test_results=[FAILED_CHECK])
    first["devops_summary"] = "The image build broke on the base layer."

    second = _devops_last_result(test_results=[FAILED_CHECK])
    second["devops_summary"] = "An entirely different narrative."
    second["devops_changes"] = [
        {
            "path": "Dockerfile",
            "description": "Rewritten description.",
            "category": "containerization",
        }
    ]

    assert build_devops_failure_signature(first) == (
        build_devops_failure_signature(second)
    )


def test_the_signature_never_interprets_rollback_prose() -> None:
    """Its absence is structural evidence; its contents are not."""

    first = _devops_last_result(
        test_results=[FAILED_CHECK],
        rollback_strategy="Redeploy the previous image tag.",
    )

    second = _devops_last_result(
        test_results=[FAILED_CHECK],
        rollback_strategy=(
            "Roll back by restoring the database snapshot and reverting "
            "the helm release to the prior revision."
        ),
    )

    assert build_devops_failure_signature(first) == (
        build_devops_failure_signature(second)
    )


def test_a_missing_rollback_strategy_changes_the_signature() -> None:
    present = build_devops_failure_signature(
        _devops_last_result(test_results=[FAILED_CHECK])
    )

    absent = build_devops_failure_signature(
        _devops_last_result(
            test_results=[FAILED_CHECK],
            rollback_strategy="",
        )
    )

    assert present != absent
    assert "rollback_missing" in absent


def test_a_missing_deployment_flag_changes_the_signature() -> None:
    signature = build_devops_failure_signature(
        _devops_last_result(
            test_results=[FAILED_CHECK],
            deployment_ready=False,
        )
    )

    assert "deployment_not_ready" in signature


def test_missing_evidence_has_its_own_structural_signature() -> None:
    assert "no_evidence" in build_devops_failure_signature(
        _devops_last_result(test_results=[])
    )


def test_a_different_failing_command_is_a_different_signature() -> None:
    other = dict(FAILED_CHECK)
    other["command"] = "npm run lint"

    assert build_devops_failure_signature(
        _devops_last_result(test_results=[FAILED_CHECK])
    ) != build_devops_failure_signature(
        _devops_last_result(test_results=[other])
    )


def test_a_successful_cycle_has_no_signature() -> None:
    assert build_devops_failure_signature(
        _devops_last_result(
            test_results=[PASSING_CHECK],
            devops_passed=True,
        )
    ) == ""


# --------------------------------------------------------------------------
# Advancing and resetting
# --------------------------------------------------------------------------


def test_a_failed_cycle_advances_the_counter() -> None:
    last_result = _devops_last_result(test_results=[FAILED_CHECK])

    advance_devops_retry_state(
        last_result,
        previous_count=0,
        previous_signature="",
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["devops_retry_count"] == 1
    assert last_result["devops_repeated_failures"] == 0
    assert last_result["devops_failure_signature"]


def test_the_same_failure_twice_records_a_repetition() -> None:
    last_result = _devops_last_result(test_results=[FAILED_CHECK])

    signature = build_devops_failure_signature(last_result)

    advance_devops_retry_state(
        last_result,
        previous_count=1,
        previous_signature=signature,
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["devops_repeated_failures"] == 1


def test_a_successful_cycle_resets_the_history() -> None:
    last_result = _devops_last_result(
        test_results=[PASSING_CHECK],
        devops_passed=True,
        retry_count=2,
        repeated=1,
        signature="stale",
    )

    advance_devops_retry_state(
        last_result,
        previous_count=2,
        previous_signature="stale",
        previous_repeated=1,
        cycle_failed=False,
    )

    assert last_result["devops_retry_count"] == 0
    assert last_result["devops_repeated_failures"] == 0
    assert last_result["devops_failure_signature"] == ""

    assert_devops_retry_budget(
        {"agents": {"devops": {"last_result": last_result}}}
    )


# --------------------------------------------------------------------------
# Persistence and restart
# --------------------------------------------------------------------------


def test_the_budget_survives_save_and_load(tmp_path: Path) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_DEVOPS_RETRIES))

    reloaded = load_state(state_path)

    assert get_devops_retry_count(reloaded) == MAX_DEVOPS_RETRIES

    with pytest.raises(NonConvergingDevOpsError):
        assert_devops_retry_budget(reloaded)


def test_restarting_the_cli_does_not_reopen_the_budget(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_DEVOPS_RETRIES))

    for _ in range(3):
        reloaded = load_state(state_path)

        with pytest.raises(NonConvergingDevOpsError):
            assert_devops_retry_budget(reloaded)

        save_state(state_path, reloaded)


def test_an_ordinary_retry_does_not_bypass_the_budget() -> None:
    state = retry_agent(
        _state(retry_count=MAX_DEVOPS_RETRIES),
        "devops",
    )

    assert state["agents"]["devops"]["status"] == "READY"

    with pytest.raises(NonConvergingDevOpsError):
        assert_devops_retry_budget(state)


def test_an_explicit_operator_reset_reopens_the_budget() -> None:
    state = reset_replan_budget(
        _state(retry_count=MAX_DEVOPS_RETRIES),
        "devops",
        source="cli:retry --reset-replan-budget",
    )

    assert get_devops_retry_count(state) == 0
    assert get_devops_repeated_failures(state) == 0
    assert get_devops_failure_signature(state) == ""
    assert state["agents"]["devops"]["status"] == "READY"

    assert_devops_retry_budget(state)

    history = state["agents"]["devops"]["replan_budget_resets"]

    assert len(history) == 1
    assert history[0]["previous_replan_count"] == MAX_DEVOPS_RETRIES
    assert history[0]["source"] == "cli:retry --reset-replan-budget"


def test_a_reset_preserves_devops_diagnostics() -> None:
    state = reset_replan_budget(
        _state(
            retry_count=MAX_DEVOPS_RETRIES,
            blockers=[
                {
                    "message": "The container registry is unreachable.",
                    "kind": "EXTERNAL_DEPENDENCY",
                    "scope": "EXTERNAL",
                    "fixable_by_agent": False,
                    "requires_human_input": True,
                    "blocking": True,
                }
            ],
        ),
        "devops",
    )

    last_result = state["agents"]["devops"]["last_result"]

    assert last_result["devops_test_results"] == [FAILED_CHECK]
    assert last_result["deployment_ready"] is True
    assert last_result["rollback_strategy"] == ROLLBACK
    assert last_result["devops_blockers"]
    assert last_result["devops_summary"] == "Deployment pipeline prepared."


def test_a_reset_is_refused_while_budget_remains() -> None:
    with pytest.raises(ReplanBudgetResetError, match="still has"):
        reset_replan_budget(_state(retry_count=0), "devops")


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


def test_the_four_budgets_are_independent() -> None:
    state = _state(retry_count=MAX_DEVOPS_RETRIES)
    state["agents"]["developer"]["last_result"] = {"replan_count": 0}
    state["agents"]["qa"]["last_result"] = {"qa_retry_count": 0}
    state["agents"]["security"]["last_result"] = {
        "security_retry_count": 0
    }

    assert_replan_budget(state)
    assert_qa_retry_budget(state)
    assert_security_retry_budget(state)

    with pytest.raises(NonConvergingDevOpsError):
        assert_devops_retry_budget(state)


# --------------------------------------------------------------------------
# Workflow level
# --------------------------------------------------------------------------


class _CountingDevOpsProvider(ModelProvider, DevOpsProvider):
    """Always fails DevOps, and counts every provider call."""

    def __init__(self) -> None:
        self.devops_calls = 0
        self.run_calls = 0

    def run(self, context):
        from ai_factory.agent_result import AgentResult

        self.run_calls += 1

        return AgentResult(
            status="COMPLETED",
            summary="DevOps agent completed.",
        )

    def generate(self, prompt: str) -> str:  # pragma: no cover
        return ""

    def validate_devops(self, prompt: str) -> DevOpsResult:
        self.devops_calls += 1

        return DevOpsResult(
            summary="The deployment pipeline does not build.",
            passed=False,
            changes=[],
            test_commands=["npm run build"],
            blockers=[],
            deployment_ready=True,
            rollback_strategy=ROLLBACK,
        )


def _devops_project(root: Path) -> Path:
    state_path = root / ".factory" / "state.yaml"

    state = _state(devops_status="READY")
    state["agents"]["devops"]["last_result"] = {}
    state["agents"]["developer"]["last_result"] = {
        "implemented_files": ["src/app.ts"],
        "implementation_results": [
            {"task_id": "US-001", "summary": "App implemented."}
        ],
    }
    state["agents"]["security"]["last_result"] = {
        "security_passed": True,
    }

    save_state(state_path, state)

    save_state(
        root / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Test Project", "type": "test"},
            "context": {"agents": {"devops": []}},
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


def _stub_devops_commands(monkeypatch) -> None:
    from ai_factory.test_runner import CommandExecutionResult

    monkeypatch.setattr(
        "ai_factory.devops_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=1,
            stdout="",
            stderr="build failed",
        ),
    )


def test_a_persistently_failing_devops_terminates_the_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The unbounded loop, reproduced and bounded."""

    state_path = _devops_project(tmp_path)
    _stub_devops_commands(monkeypatch)

    provider = _CountingDevOpsProvider()

    with pytest.raises(NonConvergingDevOpsError):
        run_workflow(project_root=tmp_path, provider=provider)

    assert provider.devops_calls <= MAX_DEVOPS_RETRIES

    state = load_state(state_path)

    assert state["agents"]["devops"]["status"] == "FAILED"
    assert state["devops_gate"]["status"] == "NOT_READY"
    assert state["agents"]["sre"]["status"] == "NOT_STARTED"


def test_no_provider_call_happens_after_exhaustion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _devops_project(tmp_path)
    _stub_devops_commands(monkeypatch)

    provider = _CountingDevOpsProvider()

    with pytest.raises(NonConvergingDevOpsError):
        run_workflow(project_root=tmp_path, provider=provider)

    spent = provider.devops_calls
    state_before = load_state(state_path)

    with pytest.raises(NonConvergingDevOpsError):
        run_next_agent(project_root=tmp_path, provider=provider)

    assert provider.devops_calls == spent
    assert provider.run_calls == spent

    assert load_state(state_path) == state_before


def test_diagnostics_survive_the_bounded_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _devops_project(tmp_path)
    _stub_devops_commands(monkeypatch)

    with pytest.raises(NonConvergingDevOpsError):
        run_workflow(
            project_root=tmp_path,
            provider=_CountingDevOpsProvider(),
        )

    last_result = load_state(state_path)["agents"]["devops"][
        "last_result"
    ]

    assert last_result["devops_test_results"]
    assert last_result["devops_test_results"][0]["passed"] is False
    assert last_result["deployment_ready"] is True
    assert last_result["rollback_strategy"] == ROLLBACK
    assert last_result["devops_summary"] == (
        "The deployment pipeline does not build."
    )
    assert last_result["devops_model_passed"] is False
    assert last_result["devops_passed"] is False
    assert last_result["devops_retry_count"] >= 1
    assert last_result["devops_failure_signature"]
