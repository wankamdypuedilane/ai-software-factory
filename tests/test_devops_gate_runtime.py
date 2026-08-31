from ai_factory.devops_gate_runtime import (
    update_devops_gate_from_state,
)


def test_update_devops_gate_marks_ready_for_review() -> None:
    state = {
        "agents": {
            "devops": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "devops_passed": True,
                    "devops_blockers": [],
                    "deployment_ready": True,
                    "devops_test_results": [
                        {
                            "passed": True,
                        }
                    ],
                    "rollback_strategy": (
                        "Redeploy previous stable release."
                    ),
                },
            }
        },
        "devops_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_devops_gate_from_state(
        state
    )

    gate = updated_state["devops_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["reasons"] == []
    assert gate["human_approval"] is False


def test_update_devops_gate_marks_not_ready() -> None:
    state = {
        "agents": {
            "devops": {
                "status": "FAILED",
                "last_result": {
                    "devops_passed": False,
                    "devops_blockers": [],
                    "deployment_ready": False,
                    "devops_test_results": [
                        {
                            "passed": False,
                        }
                    ],
                    "rollback_strategy": "",
                },
            }
        },
        "devops_gate": {
            "status": "NOT_STARTED",
            "reasons": [],
            "human_approval": False,
        },
    }

    updated_state = update_devops_gate_from_state(
        state
    )

    gate = updated_state["devops_gate"]

    assert gate["status"] == "NOT_READY"

    assert (
        "DevOps is not ready for review."
        in gate["reasons"]
    )

    assert (
        "DevOps validation did not pass."
        in gate["reasons"]
    )

    assert (
        "Deployment is not ready."
        in gate["reasons"]
    )

    assert (
        "DevOps tests failed."
        in gate["reasons"]
    )

    assert (
        "Rollback strategy is missing."
        in gate["reasons"]
    )

    assert gate["human_approval"] is False
