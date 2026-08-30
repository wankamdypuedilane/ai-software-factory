from ai_factory.development_gate_runtime import (
    update_development_gate_from_state,
)


def test_update_development_gate_marks_ready_for_review() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "implementation_blocked": False,
                    "implementation_test_failed": False,
                    "implementation_results": [
                        {
                            "task_id": "US-001",
                            "summary": "Authentication implemented.",
                            "blockers": [],
                        }
                    ],
                    "test_results": [
                        {
                            "command": "pytest",
                            "returncode": 0,
                            "passed": True,
                            "stdout": "1 passed",
                            "stderr": "",
                        }
                    ],
                },
            }
        },
        "development_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_development_gate_from_state(
        state
    )

    gate = updated_state["development_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["reasons"] == []
    assert gate["human_approval"] is False


def test_update_development_gate_marks_not_ready() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "implementation_blocked": False,
                    "implementation_test_failed": True,
                    "implementation_results": [
                        {
                            "task_id": "US-001",
                        }
                    ],
                    "test_results": [
                        {
                            "command": "pytest",
                            "returncode": 1,
                            "passed": False,
                        }
                    ],
                },
            }
        },
        "development_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_development_gate_from_state(
        state
    )

    gate = updated_state["development_gate"]

    assert gate["status"] == "NOT_READY"
    assert gate["reasons"] == [
        "Developer implementation tests failed."
    ]
    assert gate["human_approval"] is False
