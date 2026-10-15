"""Non-convergence needs two distinct failed cycles, not one.

The guard runs before a cycle exists, so at guard time only the previous
cycle's result is in state. Comparing that result with a signature
recomputed from itself is always equal: the previous implementation
therefore stopped after a single honest product failure.

Two cycles can only be compared where both are known - at write time.
"""

from pathlib import Path

import pytest

from ai_factory.project import initialize_project
from ai_factory.replan_guard import (
    MAX_DEVELOPER_REPLANS,
    NonConvergingImplementationError,
    assert_replan_budget,
    build_failure_signature,
    get_repeated_failures,
    get_replan_count,
    next_repeated_failures,
    next_replan_count,
)
from ai_factory.runtime import run_next_agent
from ai_factory.state import load_state, save_state


SIGNATURE_A = "test_failed|npm run build|npm run typecheck"
SIGNATURE_B = "test_failed|npm test -- tests/links.test.ts"


def _state(
    replan_count: int = 0,
    failure_signature: str = "",
    repeated_failures: int = 0,
) -> dict:
    return {
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "implementation_test_failed": True,
                    "failed_task_id": "LV-DEV-001",
                    "test_results": [],
                    "replan_count": replan_count,
                    "failure_signature": failure_signature,
                    "repeated_failures": repeated_failures,
                },
            }
        }
    }


def _cycle(
    previous_count: int,
    previous_signature: str,
    previous_repeated: int,
    new_signature: str,
) -> tuple[int, str, int]:
    """Advance the persisted history by one failed cycle."""

    return (
        next_replan_count(previous_count, failed=True),
        new_signature,
        next_repeated_failures(
            previous_repeated,
            previous_signature,
            new_signature,
        ),
    )


# --------------------------------------------------------------------------
# The history transition
# --------------------------------------------------------------------------


def test_a_first_failure_is_not_a_repetition() -> None:
    count, signature, repeated = _cycle(0, "", 0, SIGNATURE_A)

    assert (count, signature, repeated) == (1, SIGNATURE_A, 0)


def test_two_identical_failures_are_a_repetition() -> None:
    count, signature, repeated = _cycle(1, SIGNATURE_A, 0, SIGNATURE_A)

    assert (count, signature, repeated) == (2, SIGNATURE_A, 1)


def test_a_different_failure_resets_the_repetition() -> None:
    count, signature, repeated = _cycle(1, SIGNATURE_A, 0, SIGNATURE_B)

    assert (count, signature, repeated) == (2, SIGNATURE_B, 0)


def test_a_b_a_is_not_two_consecutive_a_failures() -> None:
    history = (0, "", 0)

    for signature in (SIGNATURE_A, SIGNATURE_B, SIGNATURE_A):
        history = _cycle(history[0], history[1], history[2], signature)

    count, signature, repeated = history

    assert signature == SIGNATURE_A
    assert repeated == 0, "alternating failures are never a repetition"
    assert count == 3, "but they consume the hard budget"


def test_a_successful_cycle_clears_the_history() -> None:
    assert next_replan_count(2, failed=False) == 0
    assert next_repeated_failures(1, SIGNATURE_A, "") == 0


# --------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------


def test_one_failed_cycle_still_allows_a_replan() -> None:
    """The exact Round-6 scenario."""

    assert_replan_budget(
        _state(
            replan_count=1,
            failure_signature=SIGNATURE_A,
            repeated_failures=0,
        )
    )


def test_a_repeated_failure_stops_before_the_hard_bound() -> None:
    with pytest.raises(
        NonConvergingImplementationError,
        match="NON_CONVERGING_IMPLEMENTATION",
    ):
        assert_replan_budget(
            _state(
                replan_count=2,
                failure_signature=SIGNATURE_A,
                repeated_failures=1,
            )
        )


def test_alternating_failures_are_stopped_by_the_hard_bound() -> None:
    assert_replan_budget(
        _state(replan_count=2, failure_signature=SIGNATURE_B)
    )

    with pytest.raises(
        NonConvergingImplementationError,
        match="not converging",
    ):
        assert_replan_budget(
            _state(
                replan_count=MAX_DEVELOPER_REPLANS,
                failure_signature=SIGNATURE_A,
                repeated_failures=0,
            )
        )


def test_the_hard_bound_remains_independent() -> None:
    """It stops even when no repetition was ever detected."""

    with pytest.raises(NonConvergingImplementationError):
        assert_replan_budget(
            _state(
                replan_count=MAX_DEVELOPER_REPLANS,
                repeated_failures=0,
            )
        )


def test_the_signature_stays_independent_of_the_task_id() -> None:
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
            "failed_task_id": "LV-DEV-002-R28",
            "test_results": [
                {"command": "npm run typecheck", "passed": False}
            ],
        }
    )

    assert first == second


def test_the_round_5_prisma_loop_is_bounded() -> None:
    """46 setup failures produced the same signature every time."""

    prisma_signature = build_failure_signature(
        {
            "implementation_test_failed": True,
            "failed_task_id": "LV-DEV-002-R3",
            "test_results": [],
        }
    )

    history = (0, "", 0)
    cycles = 0

    while True:
        try:
            assert_replan_budget(
                _state(
                    replan_count=history[0],
                    failure_signature=history[1],
                    repeated_failures=history[2],
                )
            )
        except NonConvergingImplementationError:
            break

        cycles += 1
        history = _cycle(
            history[0],
            history[1],
            history[2],
            prisma_signature,
        )

        assert cycles <= 5, "the loop must be bounded"

    assert cycles == 2, "two identical cycles, then stop"


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def test_the_history_survives_a_state_reload(tmp_path: Path) -> None:
    project_root = initialize_project("History Probe", tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    state = load_state(state_path)
    state["agents"]["developer"] = _state(
        replan_count=2,
        failure_signature=SIGNATURE_A,
        repeated_failures=1,
    )["agents"]["developer"]
    save_state(state_path, state)

    reloaded = load_state(state_path)

    assert get_replan_count(reloaded) == 2
    assert get_repeated_failures(reloaded) == 1


# --------------------------------------------------------------------------
# Workflow integration
# --------------------------------------------------------------------------


class RecordingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, context):
        self.calls += 1
        raise RuntimeError("provider reached")


def _workflow_project(
    tmp_path: Path,
    replan_count: int,
    failure_signature: str,
    repeated_failures: int,
) -> Path:
    project_root = initialize_project("Workflow Probe", tmp_path)
    state_path = project_root / ".factory" / "state.yaml"

    state = load_state(state_path)

    for agent in ("product", "ux_ui", "architect"):
        state["agents"][agent]["status"] = "APPROVED"

    state["agents"]["developer"] = {
        "status": "FAILED",
        "last_result": {
            "implementation_test_failed": True,
            "failed_task_id": "LV-DEV-001",
            "test_results": [],
            "replan_count": replan_count,
            "failure_signature": failure_signature,
            "repeated_failures": repeated_failures,
        },
    }

    save_state(state_path, state)

    return project_root


def test_workflow_allows_a_replan_after_one_failure(
    tmp_path: Path,
) -> None:
    """Round-6 regression, at workflow level."""

    project_root = _workflow_project(tmp_path, 1, SIGNATURE_A, 0)
    provider = RecordingProvider()

    with pytest.raises(RuntimeError, match="provider reached"):
        run_next_agent(
            project_root=project_root,
            provider=provider,
        )

    assert provider.calls == 1


def test_workflow_rejects_a_repetition_before_any_provider_call(
    tmp_path: Path,
) -> None:
    project_root = _workflow_project(tmp_path, 2, SIGNATURE_A, 1)
    state_path = project_root / ".factory" / "state.yaml"
    before = state_path.read_text(encoding="utf-8")

    provider = RecordingProvider()

    with pytest.raises(NonConvergingImplementationError):
        run_next_agent(
            project_root=project_root,
            provider=provider,
        )

    assert provider.calls == 0
    assert state_path.read_text(encoding="utf-8") == before


def test_workflow_rejects_the_hard_bound_before_any_provider_call(
    tmp_path: Path,
) -> None:
    project_root = _workflow_project(
        tmp_path,
        MAX_DEVELOPER_REPLANS,
        SIGNATURE_B,
        0,
    )
    state_path = project_root / ".factory" / "state.yaml"
    before = state_path.read_text(encoding="utf-8")

    provider = RecordingProvider()

    with pytest.raises(NonConvergingImplementationError):
        run_next_agent(
            project_root=project_root,
            provider=provider,
        )

    assert provider.calls == 0
    assert state_path.read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------
# Checkpoint interaction
# --------------------------------------------------------------------------


def test_a_checkpoint_carries_the_history_without_extra_code(
    tmp_path: Path,
) -> None:
    """state.yaml is a managed file, so no checkpoint change is needed."""

    from ai_factory.factory_checkpoint import (
        create_checkpoint,
        restore_checkpoint,
    )

    project_root = _workflow_project(tmp_path, 2, SIGNATURE_A, 1)

    create_checkpoint(project_root, "non-converging")

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["developer"]["last_result"]["repeated_failures"] = 0
    state["agents"]["developer"]["last_result"]["replan_count"] = 0
    save_state(state_path, state)

    assert get_repeated_failures(load_state(state_path)) == 0

    restore_checkpoint(project_root, "non-converging")

    restored = load_state(state_path)

    assert get_repeated_failures(restored) == 1
    assert get_replan_count(restored) == 2
