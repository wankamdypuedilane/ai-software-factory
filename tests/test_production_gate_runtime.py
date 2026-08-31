from ai_factory.production_gate_runtime import (
    update_production_gate_from_state,
)


def test_update_production_gate_marks_ready_for_review() -> None:
    state = {
        "approvals": {
            "sre": True,
            "production_deployment": False,
        },
        "agents": {
            "sre": {
                "status": "APPROVED",
            },
        },
        "sre_gate": {
            "status": "APPROVED",
            "reasons": [],
            "human_approval": True,
        },
        "production_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_production_gate_from_state(
        state
    )

    gate = updated_state["production_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["reasons"] == []
    assert gate["human_approval"] is False


def test_update_production_gate_marks_not_ready() -> None:
    state = {
        "approvals": {
            "sre": False,
            "production_deployment": False,
        },
        "agents": {
            "sre": {
                "status": "REVIEW_REQUIRED",
            },
        },
        "sre_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
        "production_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_production_gate_from_state(
        state
    )

    gate = updated_state["production_gate"]

    assert gate["status"] == "NOT_READY"

    assert (
        "SRE is not approved."
        in gate["reasons"]
    )

    assert (
        "SRE Gate is not approved."
        in gate["reasons"]
    )

    assert (
        "SRE Gate does not have human approval."
        in gate["reasons"]
    )

    assert (
        "SRE human approval is missing."
        in gate["reasons"]
    )

    assert gate["human_approval"] is False
