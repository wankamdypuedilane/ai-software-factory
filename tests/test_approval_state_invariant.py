"""APPROVED is owned by the approval flow.

`set-status <agent> APPROVED` was a legal transition that skipped
`activate_next_agent`, left the approval unrecorded, and could not be undone
because APPROVED is terminal. It stranded a LinkVault run permanently.
"""

from pathlib import Path

import pytest

from ai_factory.approval_runtime import apply_approval
from ai_factory.approvals import APPROVAL_AGENT_MAP
from ai_factory.transitions import set_agent_status


def _state() -> dict:
    return {
        "project": {
            "id": "probe",
            "name": "Probe",
            "phase": "discovery",
        },
        "agents": {
            "product": {"status": "REVIEW_REQUIRED"},
            "ux_ui": {"status": "NOT_STARTED"},
            "architect": {"status": "NOT_STARTED"},
            "developer": {"status": "NOT_STARTED"},
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "approvals": {
            "product_scope": False,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
    }


def test_set_status_cannot_approve_an_agent_owned_by_an_approval() -> None:
    state = _state()

    with pytest.raises(
        ValueError,
        match="approve product_scope",
    ):
        set_agent_status(
            state,
            "product",
            "APPROVED",
        )

    assert state["agents"]["product"]["status"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "approval_name,agent_name",
    sorted(APPROVAL_AGENT_MAP.items()),
)
def test_every_approval_owned_agent_is_protected(
    approval_name: str,
    agent_name: str,
) -> None:
    state = _state()
    state["agents"][agent_name]["status"] = "REVIEW_REQUIRED"

    with pytest.raises(
        ValueError,
        match=approval_name,
    ):
        set_agent_status(
            state,
            agent_name,
            "APPROVED",
        )


def test_unowned_transitions_are_unaffected() -> None:
    state = _state()

    set_agent_status(
        state,
        "ux_ui",
        "READY",
    )

    assert state["agents"]["ux_ui"]["status"] == "READY"

    set_agent_status(
        state,
        "product",
        "FAILED",
    )

    assert state["agents"]["product"]["status"] == "FAILED"


def test_apply_approval_still_reaches_approved(
    tmp_path: Path,
) -> None:
    state = _state()

    apply_approval(
        state,
        "product_scope",
        project_root=tmp_path,
    )

    assert state["agents"]["product"]["status"] == "APPROVED"


def test_an_approved_agent_always_has_its_approval_and_successor(
    tmp_path: Path,
) -> None:
    """The invariant `set-status` was able to break."""

    state = _state()

    apply_approval(
        state,
        "product_scope",
        project_root=tmp_path,
    )

    assert state["agents"]["product"]["status"] == "APPROVED"
    assert state["approvals"]["product_scope"] is True
    assert state["agents"]["ux_ui"]["status"] == "READY"


def test_reproduces_the_linkvault_strand_and_now_prevents_it(
    tmp_path: Path,
) -> None:
    """The exact command sequence that stranded the first LinkVault run."""

    state = _state()

    # ai-factory set-status product APPROVED
    with pytest.raises(ValueError):
        set_agent_status(
            state,
            "product",
            "APPROVED",
        )

    # ai-factory approve product_scope  -- still possible now
    apply_approval(
        state,
        "product_scope",
        project_root=tmp_path,
    )

    assert state["agents"]["product"]["status"] == "APPROVED"
    assert state["agents"]["ux_ui"]["status"] == "READY"
