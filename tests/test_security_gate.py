from ai_factory.security_gate import (
    evaluate_security_gate,
)


def test_security_gate_is_ready_when_validation_passes() -> None:
    security_state = {
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

    evaluation = evaluate_security_gate(
        security_state
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_security_gate_rejects_non_review_status() -> None:
    evaluation = evaluate_security_gate(
        {
            "status": "FAILED",
            "last_result": {
                "security_passed": False,
                "security_blockers": [],
                "security_test_results": [],
                "security_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Security is not ready for review."
        in evaluation.reasons
    )


def test_security_gate_rejects_missing_result() -> None:
    evaluation = evaluate_security_gate(
        {
            "status": "REVIEW_REQUIRED",
        }
    )

    assert evaluation.ready is False
    assert (
        "Security result is missing."
        in evaluation.reasons
    )


def test_security_gate_rejects_blockers() -> None:
    evaluation = evaluate_security_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "security_passed": True,
                "security_blockers": [
                    "Security environment unavailable.",
                ],
                "security_test_results": [],
                "security_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Security has unresolved blockers."
        in evaluation.reasons
    )


def test_security_gate_rejects_failed_tests() -> None:
    evaluation = evaluate_security_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "security_passed": True,
                "security_blockers": [],
                "security_test_results": [
                    {
                        "passed": False,
                    }
                ],
                "security_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Security tests failed."
        in evaluation.reasons
    )


def test_security_gate_rejects_unresolved_high_findings() -> None:
    evaluation = evaluate_security_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "security_passed": True,
                "security_blockers": [],
                "security_test_results": [],
                "security_findings": [
                    {
                        "id": "SEC-001",
                        "severity": "High",
                        "status": "OPEN",
                    }
                ],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Security has unresolved Critical or High severity findings."
        in evaluation.reasons
    )


def test_security_gate_allows_resolved_high_findings() -> None:
    evaluation = evaluate_security_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "security_passed": True,
                "security_blockers": [],
                "security_test_results": [],
                "security_findings": [
                    {
                        "id": "SEC-001",
                        "severity": "High",
                        "status": "RESOLVED",
                    }
                ],
            },
        }
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []
