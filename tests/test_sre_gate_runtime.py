from ai_factory.sre_gate_runtime import (
    update_sre_gate_from_state,
)


def test_update_sre_gate_marks_ready_for_review() -> None:
    state = {
        "agents": {
            "sre": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "sre_passed": True,
                    "sre_blockers": [],
                    "observability_ready": True,
                    "incident_readiness": True,
                    "sre_test_results": [
                        {
                            "passed": True,
                        }
                    ],
                    "sre_findings": [
                        {
                            "id": "SRE-001",
                            "severity": "Low",
                            "status": "OPEN",
                        }
                    ],
                },
            }
        },
        "sre_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_sre_gate_from_state(
        state
    )

    gate = updated_state["sre_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["reasons"] == []
    assert gate["human_approval"] is False


def test_update_sre_gate_marks_not_ready() -> None:
    state = {
        "agents": {
            "sre": {
                "status": "FAILED",
                "last_result": {
                    "sre_passed": False,
                    "sre_blockers": [],
                    "observability_ready": False,
                    "incident_readiness": False,
                    "sre_test_results": [
                        {
                            "passed": False,
                        }
                    ],
                    "sre_findings": [
                        {
                            "id": "SRE-001",
                            "severity": "High",
                            "status": "OPEN",
                        }
                    ],
                },
            }
        },
        "sre_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_sre_gate_from_state(
        state
    )

    gate = updated_state["sre_gate"]

    assert gate["status"] == "NOT_READY"

    assert (
        "SRE is not ready for review."
        in gate["reasons"]
    )

    assert (
        "SRE validation did not pass."
        in gate["reasons"]
    )

    assert (
        "Observability is not ready."
        in gate["reasons"]
    )

    assert (
        "Incident readiness is not sufficient."
        in gate["reasons"]
    )

    assert (
        "SRE tests failed."
        in gate["reasons"]
    )

    assert (
        "SRE has unresolved Critical or High severity findings."
        in gate["reasons"]
    )

    assert gate["human_approval"] is False
