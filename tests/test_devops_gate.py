from ai_factory.devops_gate import (
    evaluate_devops_gate,
)


def test_devops_gate_is_ready_when_validation_passes() -> None:
    devops_state = {
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

    evaluation = evaluate_devops_gate(
        devops_state
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_devops_gate_rejects_non_review_status() -> None:
    evaluation = evaluate_devops_gate(
        {
            "status": "FAILED",
            "last_result": {
                "devops_passed": False,
                "devops_blockers": [],
                "deployment_ready": False,
                "devops_test_results": [],
                "rollback_strategy": "",
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "DevOps is not ready for review."
        in evaluation.reasons
    )


def test_devops_gate_rejects_missing_result() -> None:
    evaluation = evaluate_devops_gate(
        {
            "status": "REVIEW_REQUIRED",
        }
    )

    assert evaluation.ready is False
    assert (
        "DevOps result is missing."
        in evaluation.reasons
    )


def test_devops_gate_rejects_blockers() -> None:
    evaluation = evaluate_devops_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "devops_passed": True,
                "devops_blockers": [
                    "Deployment credentials unavailable.",
                ],
                "deployment_ready": True,
                "devops_test_results": [],
                "rollback_strategy": "Rollback.",
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "DevOps has unresolved blockers."
        in evaluation.reasons
    )


def test_devops_gate_rejects_not_deployment_ready() -> None:
    evaluation = evaluate_devops_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "devops_passed": False,
                "devops_blockers": [],
                "deployment_ready": False,
                "devops_test_results": [],
                "rollback_strategy": "Rollback.",
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Deployment is not ready."
        in evaluation.reasons
    )


def test_devops_gate_rejects_failed_tests() -> None:
    evaluation = evaluate_devops_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "devops_passed": True,
                "devops_blockers": [],
                "deployment_ready": True,
                "devops_test_results": [
                    {
                        "passed": False,
                    }
                ],
                "rollback_strategy": "Rollback.",
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "DevOps tests failed."
        in evaluation.reasons
    )


def test_devops_gate_rejects_missing_rollback_strategy() -> None:
    evaluation = evaluate_devops_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "devops_passed": True,
                "devops_blockers": [],
                "deployment_ready": True,
                "devops_test_results": [],
                "rollback_strategy": "",
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Rollback strategy is missing."
        in evaluation.reasons
    )
