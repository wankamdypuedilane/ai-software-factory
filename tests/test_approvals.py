import pytest

from ai_factory.approvals import approve


def test_approve_sets_approval_to_true() -> None:
    state = {
        "approvals": {
            "product_scope": False,
            "design": False,
            "architecture": False,
            "production_deployment": False,
        }
    }

    updated_state = approve(
        state,
        "product_scope",
    )

    assert updated_state["approvals"]["product_scope"] is True


def test_approve_rejects_unknown_approval() -> None:
    state = {
        "approvals": {
            "product_scope": False,
        }
    }

    with pytest.raises(ValueError):
        approve(
            state,
            "unknown",
        )


def test_approve_rejects_direct_production_deployment() -> None:
    state = {
        "approvals": {
            "production_deployment": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="Production deployment approval must be applied through the Production Gate",
    ):
        approve(
            state,
            "production_deployment",
        )

    assert (
        state["approvals"]["production_deployment"]
        is False
    )
