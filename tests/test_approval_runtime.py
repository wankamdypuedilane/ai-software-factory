import pytest

from ai_factory.approval_runtime import apply_approval


def test_apply_product_scope_approval_approves_product() -> None:
    state = {
        "approvals": {
            "product_scope": False,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "product": {
                "status": "REVIEW_REQUIRED",
            },
            "ux_ui": {
                "status": "NOT_STARTED",
            },
        },
    }

    updated_state = apply_approval(
        state,
        "product_scope",
    )

    assert updated_state["approvals"]["product_scope"] is True
    assert updated_state["agents"]["product"]["status"] == "APPROVED"
    assert updated_state["agents"]["ux_ui"]["status"] == "READY"


def test_apply_design_approval_approves_ux_ui() -> None:
    state = {
        "approvals": {
            "product_scope": True,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
            },
            "architect": {
                "status": "NOT_STARTED",
            },
        },
        "design_gate": {
            "status": "READY_FOR_REVIEW",
            "groups": {
                "main": {
                    "approved": 1,
                    "total": 1,
                }
            },
            "external_blockers": [],
            "human_approval": False,
        },
    }

    updated_state = apply_approval(
        state,
        "design",
    )

    assert updated_state["approvals"]["design"] is True
    assert updated_state["agents"]["ux_ui"]["status"] == "APPROVED"
    assert updated_state["agents"]["architect"]["status"] == "READY"
    assert updated_state["design_gate"]["status"] == "APPROVED"
    assert updated_state["design_gate"]["human_approval"] is True


def test_apply_approval_rejects_agent_not_waiting_for_review() -> None:
    state = {
        "approvals": {
            "product_scope": False,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        },
        "agents": {
            "product": {
                "status": "READY",
            }
        },
    }

    with pytest.raises(
        ValueError,
        match="not waiting for review",
    ):
        apply_approval(
            state,
            "product_scope",
        )
