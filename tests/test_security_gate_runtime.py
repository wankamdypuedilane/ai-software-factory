from ai_factory.security_gate_runtime import (
    update_security_gate_from_state,
)


def test_update_security_gate_marks_ready_for_review() -> None:
    state = {
        "agents": {
            "security": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "security_passed": True,
                    "security_blockers": [],
                    "security_test_results": [
                        {
                            "passed": True,
                        }
                    ],
                    "security_findings": [
                        {
                            "id": "SEC-001",
                            "severity": "Low",
                            "status": "OPEN",
                        }
                    ],
                },
            }
        },
        "security_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_security_gate_from_state(
        state
    )

    gate = updated_state["security_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["reasons"] == []
    assert gate["human_approval"] is False


def test_update_security_gate_marks_not_ready() -> None:
    state = {
        "agents": {
            "security": {
                "status": "FAILED",
                "last_result": {
                    "security_passed": False,
                    "security_blockers": [],
                    "security_test_results": [
                        {
                            "passed": False,
                        }
                    ],
                    "security_findings": [
                        {
                            "id": "SEC-001",
                            "severity": "High",
                            "status": "OPEN",
                        }
                    ],
                },
            }
        },
        "security_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_security_gate_from_state(
        state
    )

    gate = updated_state["security_gate"]

    assert gate["status"] == "NOT_READY"

    assert (
        "Security is not ready for review."
        in gate["reasons"]
    )

    assert (
        "Security validation did not pass."
        in gate["reasons"]
    )

    assert (
        "Security tests failed."
        in gate["reasons"]
    )

    assert (
        "Security has unresolved Critical or High severity findings."
        in gate["reasons"]
    )

    assert gate["human_approval"] is False
