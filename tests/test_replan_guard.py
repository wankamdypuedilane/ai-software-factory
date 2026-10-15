"""No autonomous workflow may spend provider calls indefinitely.

LinkVault round 5 replanned LV-DEV-002 twenty-eight times on the same
failure, consuming 127 provider calls in 38 minutes with no bound.
"""

from pathlib import Path

import pytest

from ai_factory.project import initialize_project
from ai_factory.replan_guard import (
    MAX_DEVELOPER_REPLANS,
    NonConvergingImplementationError,
    assert_replan_budget,
    build_failure_signature,
    get_failure_signature,
    get_replan_count,
    next_replan_count,
)
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state


def _developer_state(
    replan_count: int = 0,
    signature: str = "",
    status: str = "FAILED",
) -> dict:
    return {
        "agents": {
            "developer": {
                "status": status,
                "last_result": {
                    "implementation_test_failed": True,
                    "failed_task_id": "LV-DEV-002-R7",
                    "test_results": [],
                    "replan_count": replan_count,
                    "failure_signature": signature,
                },
            }
        }
    }


# --------------------------------------------------------------------------
# Counter
# --------------------------------------------------------------------------


def test_replan_count_is_read_from_state() -> None:
    assert get_replan_count(_developer_state(2)) == 2
    assert get_replan_count({"agents": {}}) == 0


def test_a_failure_increments_and_a_success_resets() -> None:
    assert next_replan_count(2, failed=True) == 3
    assert next_replan_count(2, failed=False) == 0
    assert next_replan_count(0, failed=True) == 1


def test_the_budget_allows_up_to_the_limit() -> None:
    for count in range(MAX_DEVELOPER_REPLANS):
        assert_replan_budget(_developer_state(count))


def test_the_budget_stops_at_the_limit() -> None:
    with pytest.raises(
        NonConvergingImplementationError,
        match="not converging",
    ):
        assert_replan_budget(
            _developer_state(MAX_DEVELOPER_REPLANS)
        )


# --------------------------------------------------------------------------
# Repetition
# --------------------------------------------------------------------------


def test_the_failure_signature_ignores_the_renamed_task() -> None:
    first = build_failure_signature(
        {
            "implementation_test_failed": True,
            "failed_task_id": "LV-DEV-002-R7",
            "test_results": [
                {"command": "npm run typecheck", "passed": False}
            ],
        }
    )
    second = build_failure_signature(
        {
            "implementation_test_failed": True,
            "failed_task_id": "LV-DEV-002-R8",
            "test_results": [
                {"command": "npm run typecheck", "passed": False}
            ],
        }
    )

    assert first == second


def test_a_different_failure_has_a_different_signature() -> None:
    assert build_failure_signature(
        {
            "implementation_test_failed": True,
            "test_results": [
                {"command": "npm run typecheck", "passed": False}
            ],
        }
    ) != build_failure_signature(
        {
            "implementation_test_failed": True,
            "test_results": [
                {"command": "npm run build", "passed": False}
            ],
        }
    )


def test_a_repeated_signature_stops_earlier_than_the_hard_bound() -> None:
    """Repetition is a persisted fact, not something a caller asserts.

    The guard used to accept a `repeated_signature` flag that its caller
    derived by comparing a stored value with itself. It now reads the
    counter written when two distinct cycles were both known.
    """

    state = _developer_state(
        replan_count=2,
        signature="test_failed",
    )
    state["agents"]["developer"]["last_result"][
        "repeated_failures"
    ] = 1

    assert get_failure_signature(state) == "test_failed"

    with pytest.raises(
        NonConvergingImplementationError,
        match="NON_CONVERGING_IMPLEMENTATION",
    ):
        assert_replan_budget(state)


# --------------------------------------------------------------------------
# The workflow stops without spending a provider call
# --------------------------------------------------------------------------


def test_no_provider_call_once_the_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    project_root = initialize_project(
        "Convergence Probe",
        tmp_path,
    )

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)

    state["agents"]["product"]["status"] = "APPROVED"
    state["agents"]["ux_ui"]["status"] = "APPROVED"
    state["agents"]["architect"]["status"] = "APPROVED"
    state["agents"]["developer"] = {
        "status": "FAILED",
        "last_result": {
            "implementation_test_failed": True,
            "failed_task_id": "LV-DEV-002-R28",
            "test_results": [],
            "replan_count": MAX_DEVELOPER_REPLANS,
            "failure_signature": "test_failed",
        },
    }

    save_state(state_path, state)
    before = state_path.read_text(encoding="utf-8")

    class RecordingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, context):
            self.calls += 1
            raise AssertionError(
                "The provider must not be called past the replan budget."
            )

    provider = RecordingProvider()

    with pytest.raises(NonConvergingImplementationError):
        run_next_agent(
            project_root=project_root,
            provider=provider,
        )

    assert provider.calls == 0

    # The workflow is untouched and the diagnostics survive.
    assert state_path.read_text(encoding="utf-8") == before

    reloaded = load_state(state_path)
    developer = reloaded["agents"]["developer"]

    assert developer["status"] == "FAILED"
    assert (
        developer["last_result"]["failed_task_id"]
        == "LV-DEV-002-R28"
    )
    assert (
        developer["last_result"]["replan_count"]
        == MAX_DEVELOPER_REPLANS
    )


def test_the_counter_survives_a_cli_restart(
    tmp_path: Path,
) -> None:
    """Reading state from disk must not reset the budget."""

    project_root = initialize_project(
        "Restart Probe",
        tmp_path,
    )

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["developer"] = {
        "status": "FAILED",
        "last_result": {
            "implementation_test_failed": True,
            "test_results": [],
            "replan_count": 2,
            "failure_signature": "test_failed",
        },
    }
    save_state(state_path, state)

    assert get_replan_count(load_state(state_path)) == 2
