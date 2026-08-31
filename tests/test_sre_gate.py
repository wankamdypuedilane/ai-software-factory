from ai_factory.sre_gate import (
    evaluate_sre_gate,
)


def test_sre_gate_is_ready_when_validation_passes() -> None:
    sre_state = {
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

    evaluation = evaluate_sre_gate(
        sre_state
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []


def test_sre_gate_rejects_non_review_status() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "FAILED",
            "last_result": {
                "sre_passed": False,
                "sre_blockers": [],
                "observability_ready": False,
                "incident_readiness": False,
                "sre_test_results": [],
                "sre_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "SRE is not ready for review."
        in evaluation.reasons
    )


def test_sre_gate_rejects_missing_result() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
        }
    )

    assert evaluation.ready is False
    assert (
        "SRE result is missing."
        in evaluation.reasons
    )


def test_sre_gate_rejects_blockers() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "sre_passed": True,
                "sre_blockers": [
                    "Telemetry environment unavailable.",
                ],
                "observability_ready": True,
                "incident_readiness": True,
                "sre_test_results": [],
                "sre_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "SRE has unresolved blockers."
        in evaluation.reasons
    )


def test_sre_gate_rejects_observability_not_ready() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "sre_passed": False,
                "sre_blockers": [],
                "observability_ready": False,
                "incident_readiness": True,
                "sre_test_results": [],
                "sre_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Observability is not ready."
        in evaluation.reasons
    )


def test_sre_gate_rejects_incident_readiness_missing() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "sre_passed": False,
                "sre_blockers": [],
                "observability_ready": True,
                "incident_readiness": False,
                "sre_test_results": [],
                "sre_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "Incident readiness is not sufficient."
        in evaluation.reasons
    )


def test_sre_gate_rejects_failed_tests() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "sre_passed": True,
                "sre_blockers": [],
                "observability_ready": True,
                "incident_readiness": True,
                "sre_test_results": [
                    {
                        "passed": False,
                    }
                ],
                "sre_findings": [],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "SRE tests failed."
        in evaluation.reasons
    )


def test_sre_gate_rejects_unresolved_high_findings() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "sre_passed": True,
                "sre_blockers": [],
                "observability_ready": True,
                "incident_readiness": True,
                "sre_test_results": [],
                "sre_findings": [
                    {
                        "id": "SRE-001",
                        "severity": "High",
                        "status": "OPEN",
                    }
                ],
            },
        }
    )

    assert evaluation.ready is False
    assert (
        "SRE has unresolved Critical or High severity findings."
        in evaluation.reasons
    )


def test_sre_gate_allows_resolved_high_findings() -> None:
    evaluation = evaluate_sre_gate(
        {
            "status": "REVIEW_REQUIRED",
            "last_result": {
                "sre_passed": True,
                "sre_blockers": [],
                "observability_ready": True,
                "incident_readiness": True,
                "sre_test_results": [],
                "sre_findings": [
                    {
                        "id": "SRE-001",
                        "severity": "High",
                        "status": "RESOLVED",
                    }
                ],
            },
        }
    )

    assert evaluation.ready is True
    assert evaluation.reasons == []
