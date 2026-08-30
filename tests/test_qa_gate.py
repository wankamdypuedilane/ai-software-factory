from ai_factory.qa_gate import (
    evaluate_qa_gate,
)


def test_qa_gate_is_ready_when_validation_passes() -> None:
    qa_state = {
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

    evaluation = evaluate_qa_gate(
        qa_state
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_qa_gate_rejects_non_review_status() -> None:
    evaluation = evaluate_qa_gate(
        {
            "status": "FAILED",
            "last_result": {
                "qa_passed": False,
                "qa_blockers": [],
                "qa_test_results": [],
                "qa_defects": [],
            },
        }
    )

    assert evaluation.ready is False
    assert "QA is not ready for review." in evaluation.reasons


def test_qa_gate_rejects_missing_result() -> None:
    evaluation = evaluate_qa_gate(
        {
            "status": "REVIEW_REQUIRED",
        }
    )

    assert evaluation.ready is False
    assert "QA result is missing." in evaluation.reasons


def test_qa_gate_rejects_blockers() -> None:
    evaluation = evaluate_qa_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "qa_passed": True,
                "qa_blockers": [
                    "Test environment unavailable.",
                ],
                "qa_test_results": [],
                "qa_defects": [],
            },
        }
    )

    assert evaluation.ready is False
    assert "QA has unresolved blockers." in evaluation.reasons


def test_qa_gate_rejects_failed_tests() -> None:
    evaluation = evaluate_qa_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "qa_passed": True,
                "qa_blockers": [],
                "qa_test_results": [
                    {
                        "passed": False,
                    }
                ],
                "qa_defects": [],
            },
        }
    )

    assert evaluation.ready is False
    assert "QA tests failed." in evaluation.reasons


def test_qa_gate_rejects_critical_or_high_defects() -> None:
    evaluation = evaluate_qa_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "qa_passed": True,
                "qa_blockers": [],
                "qa_test_results": [],
                "qa_defects": [
                    {
                        "id": "QA-001",
                        "severity": "High",
                    }
                ],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "QA has unresolved Critical or High severity defects."
        in evaluation.reasons
    )
