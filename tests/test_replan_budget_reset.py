"""Opening a new replan budget must be a deliberate operator act.

A bounded autonomous search may legitimately stop. The operator then needs a
way to authorize a new bounded window - without editing internal state, and
without ordinary `retry` silently recreating an unbounded loop.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from ai_factory.factory_checkpoint import (
    create_checkpoint,
    restore_checkpoint,
)
from ai_factory.project import initialize_project
from ai_factory.replan_guard import (
    MAX_DEVELOPER_REPLANS,
    NonConvergingImplementationError,
    ReplanBudgetResetError,
    assert_replan_budget,
    get_repeated_failures,
    get_replan_count,
    get_failure_signature,
    reset_replan_budget,
)
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state
from ai_factory.transitions import retry_agent


SIGNATURE = "test_failed|npm run build|npm run typecheck"


def _exhausted_developer(
    status: str = "FAILED",
    replan_count: int = MAX_DEVELOPER_REPLANS,
    repeated_failures: int = 0,
) -> dict:
    return {
        "status": status,
        "last_result": {
            "status": "COMPLETED",
            "summary": "Implementation attempted.",
            "failed_task_id": "LV-DEV-004",
            "implementation_test_failed": True,
            "implementation_results": [
                {"task_id": "LV-DEV-004", "files": ["src/app.ts"]}
            ],
            "implemented_files": ["src/app.ts"],
            "test_results": [
                {
                    "command": "npm run typecheck",
                    "passed": False,
                    "stdout": "error TS2322",
                    "stderr": "",
                }
            ],
            "replan_count": replan_count,
            "failure_signature": SIGNATURE,
            "repeated_failures": repeated_failures,
        },
    }


def _state(**kwargs) -> dict:
    return {
        "project": {
            "id": "probe",
            "name": "Probe",
            "phase": "implementation",
        },
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": _exhausted_developer(**kwargs),
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
        },
        "development_gate": {
            "status": "NOT_READY",
            "human_approval": False,
        },
    }


# --------------------------------------------------------------------------
# Ordinary retry must not reopen the budget
# --------------------------------------------------------------------------


def test_ordinary_retry_preserves_the_exhausted_budget() -> None:
    state = _state()

    retry_agent(state, "developer")

    assert state["agents"]["developer"]["status"] == "READY"
    assert get_replan_count(state) == MAX_DEVELOPER_REPLANS
    assert get_failure_signature(state) == SIGNATURE


def test_the_guard_still_refuses_after_an_ordinary_retry() -> None:
    state = _state()

    retry_agent(state, "developer")

    with pytest.raises(
        NonConvergingImplementationError,
        match="not converging",
    ):
        assert_replan_budget(state)


def test_ordinary_retry_preserves_a_remaining_budget() -> None:
    """A retry with budget left keeps the history so it can still run out."""

    state = _state(replan_count=1)

    retry_agent(state, "developer")

    assert get_replan_count(state) == 1
    assert_replan_budget(state)


# --------------------------------------------------------------------------
# The explicit reset
# --------------------------------------------------------------------------


def test_the_reset_clears_the_three_history_fields() -> None:
    state = _state()

    reset_replan_budget(state)

    assert get_replan_count(state) == 0
    assert get_failure_signature(state) == ""
    assert get_repeated_failures(state) == 0


def test_the_reset_makes_the_developer_retryable() -> None:
    state = _state()

    reset_replan_budget(state)

    assert state["agents"]["developer"]["status"] == "READY"
    assert_replan_budget(state)


def test_the_reset_preserves_the_diagnostics() -> None:
    state = _state()

    reset_replan_budget(state)

    last = state["agents"]["developer"]["last_result"]

    assert last["failed_task_id"] == "LV-DEV-004"
    assert last["implementation_test_failed"] is True
    assert last["test_results"][0]["stdout"] == "error TS2322"
    assert last["implementation_results"][0]["task_id"] == "LV-DEV-004"
    assert last["implemented_files"] == ["src/app.ts"]


def test_the_reset_does_not_open_the_development_gate() -> None:
    state = _state()

    reset_replan_budget(state)

    assert state["development_gate"]["status"] == "NOT_READY"
    assert state["development_gate"]["human_approval"] is False


def test_a_reset_after_a_repetition_is_allowed() -> None:
    state = _state(replan_count=2, repeated_failures=1)

    reset_replan_budget(state)

    assert get_repeated_failures(state) == 0
    assert_replan_budget(state)


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------


def test_the_reset_is_refused_for_an_approved_developer() -> None:
    state = _state(status="APPROVED")

    with pytest.raises(
        ReplanBudgetResetError,
        match="FAILED",
    ):
        reset_replan_budget(state)

    assert get_replan_count(state) == MAX_DEVELOPER_REPLANS


def test_the_reset_is_refused_while_budget_remains() -> None:
    state = _state(replan_count=1, repeated_failures=0)

    with pytest.raises(
        ReplanBudgetResetError,
        match="still has",
    ):
        reset_replan_budget(state)

    assert get_replan_count(state) == 1


def test_the_reset_is_refused_for_an_unbudgeted_agent() -> None:
    state = _state()

    with pytest.raises(
        ReplanBudgetResetError,
        match="qa",
    ):
        reset_replan_budget(state, agent_name="qa")


def test_the_reset_is_refused_for_an_unknown_agent() -> None:
    state = _state()

    with pytest.raises(ReplanBudgetResetError):
        reset_replan_budget(state, agent_name="nonexistent")


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------


def test_the_reset_is_recorded_on_the_agent() -> None:
    state = _state()

    reset_replan_budget(state, source="cli:retry --reset-replan-budget")

    resets = state["agents"]["developer"]["replan_budget_resets"]

    assert len(resets) == 1
    assert resets[0]["previous_replan_count"] == MAX_DEVELOPER_REPLANS
    assert resets[0]["previous_failure_signature"] == SIGNATURE
    assert resets[0]["previous_repeated_failures"] == 0
    assert resets[0]["source"] == "cli:retry --reset-replan-budget"
    assert resets[0]["at"]


def test_repeated_resets_accumulate_without_surprises() -> None:
    state = _state()

    reset_replan_budget(state)

    # The developer is READY with a fresh budget: nothing to reopen.
    with pytest.raises(ReplanBudgetResetError, match="still has"):
        reset_replan_budget(state)

    # Back to FAILED but with budget left: refused on the budget instead.
    state["agents"]["developer"]["status"] = "FAILED"

    with pytest.raises(ReplanBudgetResetError, match="still has"):
        reset_replan_budget(state)

    # After exhausting the new window, another reset is legal.
    state["agents"]["developer"]["last_result"][
        "replan_count"
    ] = MAX_DEVELOPER_REPLANS

    reset_replan_budget(state)

    resets = state["agents"]["developer"]["replan_budget_resets"]

    assert len(resets) == 2
    assert get_replan_count(state) == 0


# --------------------------------------------------------------------------
# Workflow and files
# --------------------------------------------------------------------------


def _project(tmp_path: Path, **kwargs) -> Path:
    project_root = initialize_project("Reset Probe", tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    state = load_state(state_path)
    seeded = _state(**kwargs)
    state["agents"] = seeded["agents"]
    state["approvals"] = seeded["approvals"]
    state["development_gate"] = seeded["development_gate"]
    state["project"]["phase"] = "implementation"

    save_state(state_path, state)

    return project_root


class RecordingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, context):
        self.calls += 1
        raise RuntimeError("provider reached")


def test_the_next_run_reaches_the_provider_after_a_reset(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    state = load_state(state_path)
    reset_replan_budget(state)
    save_state(state_path, state)

    provider = RecordingProvider()

    with pytest.raises(RuntimeError, match="provider reached"):
        run_next_agent(
            project_root=project_root,
            provider=provider,
        )

    assert provider.calls == 1


def test_the_reset_does_not_touch_project_files(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)

    source = project_root / "src"
    source.mkdir()
    (source / "app.ts").write_text(
        "export const app = 1;\n",
        encoding="utf-8",
    )

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    reset_replan_budget(state)
    save_state(state_path, state)

    assert (source / "app.ts").read_text(
        encoding="utf-8",
    ) == "export const app = 1;\n"


# --------------------------------------------------------------------------
# Checkpoint
# --------------------------------------------------------------------------


def test_a_checkpoint_restore_reverses_the_reset(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    create_checkpoint(project_root, "exhausted")

    state = load_state(state_path)
    reset_replan_budget(state)
    save_state(state_path, state)

    assert get_replan_count(load_state(state_path)) == 0

    restore_checkpoint(project_root, "exhausted")

    restored = load_state(state_path)

    assert get_replan_count(restored) == MAX_DEVELOPER_REPLANS
    assert get_failure_signature(restored) == SIGNATURE
    assert "replan_budget_resets" not in restored["agents"]["developer"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_the_cli_explains_that_a_new_budget_was_opened(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_factory.cli",
            "retry",
            "developer",
            "--reset-replan-budget",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    output = completed.stdout + completed.stderr

    assert completed.returncode == 0, output
    assert "replanning budget" in output.lower()
    assert "was opened" in output.lower()
    assert "diagnostics" in output.lower()
    assert str(MAX_DEVELOPER_REPLANS) in output

    assert get_replan_count(
        load_state(project_root / ".factory" / "state.yaml")
    ) == 0


def test_the_plain_cli_retry_does_not_reset(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)

    completed = subprocess.run(
        [sys.executable, "-m", "ai_factory.cli", "retry", "developer"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0

    state = load_state(project_root / ".factory" / "state.yaml")

    assert state["agents"]["developer"]["status"] == "READY"
    assert get_replan_count(state) == MAX_DEVELOPER_REPLANS
