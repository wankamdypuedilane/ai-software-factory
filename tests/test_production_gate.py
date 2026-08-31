from ai_factory.production_gate import (
    evaluate_production_gate,
)


def test_production_gate_is_ready_when_sre_is_fully_approved() -> None:
    state = {
        "approvals": {
            "sre": True,
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
    }

    evaluation = evaluate_production_gate(
        state
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_production_gate_rejects_unapproved_sre_agent() -> None:
    state = {
        "approvals": {
            "sre": True,
        },
        "agents": {
            "sre": {
                "status": "REVIEW_REQUIRED",
            },
        },
        "sre_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
    }

    evaluation = evaluate_production_gate(
        state
    )

    assert evaluation.ready is False
    assert (
        "SRE is not approved."
        in evaluation.reasons
    )


def test_production_gate_rejects_unapproved_sre_gate() -> None:
    state = {
        "approvals": {
            "sre": True,
        },
        "agents": {
            "sre": {
                "status": "APPROVED",
            },
        },
        "sre_gate": {
            "status": "READY_FOR_REVIEW",
            "human_approval": False,
        },
    }

    evaluation = evaluate_production_gate(
        state
    )

    assert evaluation.ready is False

    assert (
        "SRE Gate is not approved."
        in evaluation.reasons
    )

    assert (
        "SRE Gate does not have human approval."
        in evaluation.reasons
    )


def test_production_gate_rejects_missing_sre_approval() -> None:
    state = {
        "approvals": {
            "sre": False,
        },
        "agents": {
            "sre": {
                "status": "APPROVED",
            },
        },
        "sre_gate": {
            "status": "APPROVED",
            "human_approval": True,
        },
    }

    evaluation = evaluate_production_gate(
        state
    )

    assert evaluation.ready is False

    assert (
        "SRE human approval is missing."
        in evaluation.reasons
    )


def test_production_gate_rejects_missing_sre_gate() -> None:
    state = {
        "approvals": {
            "sre": True,
        },
        "agents": {
            "sre": {
                "status": "APPROVED",
            },
        },
    }

    evaluation = evaluate_production_gate(
        state
    )

    assert evaluation.ready is False

    assert (
        "Project state does not contain a valid SRE Gate."
        in evaluation.reasons
    )
