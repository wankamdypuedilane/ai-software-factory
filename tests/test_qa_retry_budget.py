"""QA may retry. It may not retry forever.

`get_next_agent` returns any agent whose status is READY or FAILED, and
`run_workflow` loops until it returns None. The Developer is bounded by
`assert_replan_budget`; QA had no equivalent, so a QA agent that kept failing
was selected again, called the provider again, failed again, indefinitely.
Making QA success depend on executed evidence turned that from a latent
defect into an observable hang.

QA is bounded more tightly than the Developer on purpose: a QA cycle
re-validates a workspace that QA itself never changes, so a third attempt
against identical artifacts has no new information to work with.
"""

from pathlib import Path

import pytest

from ai_factory.providers import ModelProvider, QAProvider
from ai_factory.qa_result import QAResult
from ai_factory.qa_retry_guard import (
    MAX_QA_RETRIES,
    NonConvergingQAError,
    advance_qa_retry_state,
    assert_qa_retry_budget,
    build_qa_failure_signature,
    get_qa_failure_signature,
    get_qa_repeated_failures,
    get_qa_retry_count,
)
from ai_factory.replan_guard import (
    MAX_DEVELOPER_REPLANS,
    assert_replan_budget,
    reset_replan_budget,
)
from ai_factory.runtime import run_next_agent, run_workflow
from ai_factory.state import load_state, save_state
from ai_factory.transitions import retry_agent


FAILED_CHECK = {
    "command": "npm test -- src/checkout.test.ts",
    "returncode": 1,
    "passed": False,
    "stdout": "",
    "stderr": "AssertionError",
}

PASSING_CHECK = {
    "command": "npm test -- src/checkout.test.ts",
    "returncode": 0,
    "passed": True,
    "stdout": "",
    "stderr": "",
}


def _qa_last_result(
    retry_count: int = 0,
    repeated: int = 0,
    signature: str = "",
    test_results: list[dict] | None = None,
    defects: list[dict] | None = None,
    blockers: list[dict] | None = None,
    qa_passed: bool = False,
) -> dict:
    return {
        "qa_summary": "QA validation completed.",
        "qa_model_passed": qa_passed,
        "qa_passed": qa_passed,
        "qa_test_results": (
            test_results if test_results is not None else [FAILED_CHECK]
        ),
        "qa_defects": defects or [],
        "qa_blockers": blockers or [],
        "qa_retry_count": retry_count,
        "qa_repeated_failures": repeated,
        "qa_failure_signature": signature,
    }


def _state(qa_status: str = "FAILED", **kwargs) -> dict:
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
                "status": qa_status,
                "last_result": _qa_last_result(**kwargs),
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


# --------------------------------------------------------------------------
# The bound
# --------------------------------------------------------------------------


def test_a_first_qa_failure_may_be_retried() -> None:
    assert_qa_retry_budget(_state(retry_count=1))


def test_the_bound_is_finite_and_conservative() -> None:
    assert MAX_QA_RETRIES == 2
    assert MAX_QA_RETRIES < MAX_DEVELOPER_REPLANS


def test_repeated_qa_failures_cannot_loop_forever() -> None:
    with pytest.raises(NonConvergingQAError, match="NON_CONVERGING_QA"):
        assert_qa_retry_budget(
            _state(retry_count=MAX_QA_RETRIES)
        )


def test_an_identical_repeated_failure_stops_earlier() -> None:
    with pytest.raises(NonConvergingQAError):
        assert_qa_retry_budget(
            _state(retry_count=1, repeated=1)
        )


def test_the_guard_reads_only_persisted_counters() -> None:
    """It cannot derive a repetition it was not told about."""

    assert_qa_retry_budget(_state(retry_count=0, repeated=0))
    assert_qa_retry_budget(_state(retry_count=1, repeated=0))


# --------------------------------------------------------------------------
# The signature is built from structured evidence only
# --------------------------------------------------------------------------


def test_the_signature_uses_failed_commands_and_engine_reasons() -> None:
    signature = build_qa_failure_signature(
        _qa_last_result(test_results=[FAILED_CHECK])
    )

    assert "failed_checks" in signature
    assert "npm test -- src/checkout.test.ts" in signature


def test_the_signature_ignores_prose() -> None:
    """Summaries, defect titles and model wording change nothing."""

    first = _qa_last_result(test_results=[FAILED_CHECK])
    first["qa_summary"] = "Checkout totals are wrong in three scenarios."

    second = _qa_last_result(test_results=[FAILED_CHECK])
    second["qa_summary"] = (
        "A completely different narrative about the same failure."
    )
    second["qa_defects"] = [
        {
            "id": "QA-777",
            "title": "Renamed defect",
            "severity": "Low",
            "expected": "x",
            "actual": "y",
        }
    ]

    assert build_qa_failure_signature(first) == (
        build_qa_failure_signature(second)
    )


def test_missing_evidence_has_its_own_structural_signature() -> None:
    signature = build_qa_failure_signature(
        _qa_last_result(test_results=[])
    )

    assert "no_evidence" in signature
    assert signature != build_qa_failure_signature(
        _qa_last_result(test_results=[FAILED_CHECK])
    )


def test_a_different_failing_command_is_a_different_signature() -> None:
    other = dict(FAILED_CHECK)
    other["command"] = "npm test -- src/cart.test.ts"

    assert build_qa_failure_signature(
        _qa_last_result(test_results=[FAILED_CHECK])
    ) != build_qa_failure_signature(
        _qa_last_result(test_results=[other])
    )


def test_a_successful_cycle_has_no_signature() -> None:
    assert build_qa_failure_signature(
        _qa_last_result(
            test_results=[PASSING_CHECK],
            qa_passed=True,
        )
    ) == ""


# --------------------------------------------------------------------------
# Advancing and resetting the persisted history
# --------------------------------------------------------------------------


def test_a_failed_cycle_advances_the_counter() -> None:
    last_result = _qa_last_result(test_results=[FAILED_CHECK])

    advance_qa_retry_state(
        last_result,
        previous_count=0,
        previous_signature="",
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["qa_retry_count"] == 1
    assert last_result["qa_repeated_failures"] == 0
    assert last_result["qa_failure_signature"]


def test_the_same_failure_twice_records_a_repetition() -> None:
    last_result = _qa_last_result(test_results=[FAILED_CHECK])

    signature = build_qa_failure_signature(last_result)

    advance_qa_retry_state(
        last_result,
        previous_count=1,
        previous_signature=signature,
        previous_repeated=0,
        cycle_failed=True,
    )

    assert last_result["qa_repeated_failures"] == 1


def test_a_successful_cycle_resets_the_history() -> None:
    last_result = _qa_last_result(
        test_results=[PASSING_CHECK],
        qa_passed=True,
        retry_count=2,
        repeated=1,
        signature="stale",
    )

    advance_qa_retry_state(
        last_result,
        previous_count=2,
        previous_signature="stale",
        previous_repeated=1,
        cycle_failed=False,
    )

    assert last_result["qa_retry_count"] == 0
    assert last_result["qa_repeated_failures"] == 0
    assert last_result["qa_failure_signature"] == ""

    assert_qa_retry_budget(
        {"agents": {"qa": {"last_result": last_result}}}
    )


# --------------------------------------------------------------------------
# The budget survives persistence and restart
# --------------------------------------------------------------------------


def test_the_budget_survives_save_and_load(tmp_path: Path) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_QA_RETRIES))

    reloaded = load_state(state_path)

    assert get_qa_retry_count(reloaded) == MAX_QA_RETRIES

    with pytest.raises(NonConvergingQAError):
        assert_qa_retry_budget(reloaded)


def test_restarting_the_cli_does_not_reopen_the_budget(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".factory" / "state.yaml"

    save_state(state_path, _state(retry_count=MAX_QA_RETRIES))

    for _ in range(3):
        reloaded = load_state(state_path)

        with pytest.raises(NonConvergingQAError):
            assert_qa_retry_budget(reloaded)

        save_state(state_path, reloaded)


def test_an_ordinary_retry_does_not_circumvent_the_budget() -> None:
    state = _state(retry_count=MAX_QA_RETRIES)

    state = retry_agent(state, "qa")

    assert state["agents"]["qa"]["status"] == "READY"

    with pytest.raises(NonConvergingQAError):
        assert_qa_retry_budget(state)


def test_an_explicit_operator_reset_reopens_the_budget() -> None:
    state = _state(retry_count=MAX_QA_RETRIES)

    state = reset_replan_budget(
        state,
        "qa",
        source="cli:retry --reset-replan-budget",
    )

    assert get_qa_retry_count(state) == 0
    assert get_qa_repeated_failures(state) == 0
    assert get_qa_failure_signature(state) == ""
    assert state["agents"]["qa"]["status"] == "READY"

    assert_qa_retry_budget(state)

    history = state["agents"]["qa"]["replan_budget_resets"]

    assert len(history) == 1
    assert history[0]["previous_replan_count"] == MAX_QA_RETRIES


def test_a_reset_preserves_qa_diagnostics() -> None:
    state = _state(
        retry_count=MAX_QA_RETRIES,
        defects=[{"id": "QA-1", "severity": "Critical"}],
        blockers=[
            {
                "message": "Staging is unavailable.",
                "kind": "EXTERNAL_DEPENDENCY",
                "scope": "EXTERNAL",
                "fixable_by_agent": False,
                "requires_human_input": True,
                "blocking": True,
            }
        ],
    )

    state = reset_replan_budget(state, "qa")

    last_result = state["agents"]["qa"]["last_result"]

    assert last_result["qa_test_results"] == [FAILED_CHECK]
    assert last_result["qa_defects"] == [
        {"id": "QA-1", "severity": "Critical"}
    ]
    assert last_result["qa_blockers"]
    assert last_result["qa_summary"] == "QA validation completed."


def test_a_reset_is_refused_while_budget_remains() -> None:
    from ai_factory.replan_guard import ReplanBudgetResetError

    with pytest.raises(ReplanBudgetResetError, match="still has"):
        reset_replan_budget(_state(retry_count=0), "qa")


# --------------------------------------------------------------------------
# Developer behaviour is untouched
# --------------------------------------------------------------------------


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


def test_the_qa_budget_is_independent_of_the_developer_budget() -> None:
    state = _state(retry_count=MAX_QA_RETRIES)
    state["agents"]["developer"]["last_result"] = {
        "replan_count": 0,
        "repeated_failures": 0,
        "failure_signature": "",
    }

    assert_replan_budget(state)

    with pytest.raises(NonConvergingQAError):
        assert_qa_retry_budget(state)


# --------------------------------------------------------------------------
# Workflow level: the loop terminates and costs a bounded number of calls
# --------------------------------------------------------------------------


class _CountingQAProvider(ModelProvider, QAProvider):
    """Always fails QA, and counts every provider call it receives."""

    def __init__(self) -> None:
        self.qa_calls = 0
        self.run_calls = 0

    def run(self, context):
        from ai_factory.agent_result import AgentResult

        self.run_calls += 1

        return AgentResult(
            status="COMPLETED",
            summary="QA agent completed.",
        )

    def generate(self, prompt: str) -> str:  # pragma: no cover
        return ""

    def validate_qa(self, prompt: str) -> QAResult:
        self.qa_calls += 1

        return QAResult(
            summary="QA validation failed.",
            passed=False,
            test_commands=["npm test -- src/checkout.test.ts"],
        )


def _qa_project(root: Path) -> Path:
    state_path = root / ".factory" / "state.yaml"

    state = _state(qa_status="READY")
    state["agents"]["qa"]["last_result"] = {}
    state["agents"]["developer"]["last_result"] = {
        "implemented_files": ["src/checkout.ts"],
        "implementation_results": [
            {"task_id": "US-001", "summary": "Checkout implemented."}
        ],
    }

    save_state(state_path, state)

    save_state(
        root / ".factory" / "project.yaml",
        {
            "schema_version": 1,
            "project": {"name": "Test Project", "type": "test"},
            "context": {"agents": {"qa": []}},
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


def _stub_qa_commands(monkeypatch) -> None:
    from ai_factory.test_runner import CommandExecutionResult

    monkeypatch.setattr(
        "ai_factory.qa_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=1,
            stdout="",
            stderr="AssertionError",
        ),
    )


def test_a_persistently_failing_qa_terminates_the_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The observed hang, reproduced and bounded."""

    state_path = _qa_project(tmp_path)
    _stub_qa_commands(monkeypatch)

    provider = _CountingQAProvider()

    with pytest.raises(NonConvergingQAError):
        run_workflow(
            project_root=tmp_path,
            provider=provider,
        )

    assert provider.qa_calls <= MAX_QA_RETRIES

    state = load_state(state_path)

    assert state["agents"]["qa"]["status"] == "FAILED"
    assert state["qa_gate"]["status"] == "NOT_READY"
    assert state["agents"]["security"]["status"] == "NOT_STARTED"


def test_no_provider_call_happens_after_exhaustion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _qa_project(tmp_path)
    _stub_qa_commands(monkeypatch)

    provider = _CountingQAProvider()

    with pytest.raises(NonConvergingQAError):
        run_workflow(project_root=tmp_path, provider=provider)

    spent = provider.qa_calls
    state_before = load_state(state_path).copy()

    with pytest.raises(NonConvergingQAError):
        run_next_agent(project_root=tmp_path, provider=provider)

    assert provider.qa_calls == spent
    assert provider.run_calls == spent

    assert load_state(state_path) == state_before


def test_diagnostics_survive_the_bounded_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = _qa_project(tmp_path)
    _stub_qa_commands(monkeypatch)

    with pytest.raises(NonConvergingQAError):
        run_workflow(
            project_root=tmp_path,
            provider=_CountingQAProvider(),
        )

    last_result = load_state(state_path)["agents"]["qa"]["last_result"]

    assert last_result["qa_test_results"]
    assert last_result["qa_test_results"][0]["passed"] is False
    assert last_result["qa_summary"] == "QA validation failed."
    assert last_result["qa_model_passed"] is False
    assert last_result["qa_passed"] is False
    assert last_result["qa_retry_count"] >= 1
    assert last_result["qa_failure_signature"]
