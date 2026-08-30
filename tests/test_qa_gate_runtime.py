from ai_factory.qa_gate_runtime import (
    update_qa_gate_from_state,
)


def test_update_qa_gate_marks_ready_for_review() -> None:
    state = {
        "agents": {
            "qa": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "qa_passed": True,
                    "qa_blockers": [],
                    "qa_test_results": [
                        {
                            "passed": True,
                        }
                    ],
                    "qa_defects": [
                        {
                            "id": "QA-001",
                            "severity": "Low",
                        }
                    ],
                },
            }
        },
        "qa_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_qa_gate_from_state(
        state
    )

    gate = updated_state["qa_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["reasons"] == []
    assert gate["human_approval"] is False


def test_update_qa_gate_marks_not_ready() -> None:
    state = {
        "agents": {
            "qa": {
                "status": "FAILED",
                "last_result": {
                    "qa_passed": False,
                    "qa_blockers": [],
                    "qa_test_results": [
                        {
                            "passed": False,
                        }
                    ],
                    "qa_defects": [],
                },
            }
        },
        "qa_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_qa_gate_from_state(
        state
    )

    gate = updated_state["qa_gate"]

    assert gate["status"] == "NOT_READY"

    assert "QA is not ready for review." in gate["reasons"]
    assert "QA validation did not pass." in gate["reasons"]
    assert "QA tests failed." in gate["reasons"]

    assert gate["human_approval"] is False
