from ai_factory.development_gate import (
    evaluate_development_gate,
)


def test_development_gate_is_ready_for_valid_implementation() -> None:
    developer_state = {
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

    result = evaluate_development_gate(
        developer_state
    )

    assert result.ready is True
    assert result.reasons == []


def test_development_gate_rejects_missing_result() -> None:
    result = evaluate_development_gate(
        {
            "status": "REVIEW_REQUIRED",
        }
    )

    assert result.ready is False
    assert result.reasons == [
        "Developer does not contain a valid result."
    ]


def test_development_gate_rejects_blocked_implementation() -> None:
    result = evaluate_development_gate(
        {
            "last_result": {
                "implementation_blocked": True,
            }
        }
    )

    assert result.ready is False
    assert result.reasons == [
        "Developer implementation is blocked."
    ]


def test_development_gate_rejects_failed_implementation_tests() -> None:
    result = evaluate_development_gate(
        {
            "last_result": {
                "implementation_blocked": False,
                "implementation_test_failed": True,
            }
        }
    )

    assert result.ready is False
    assert result.reasons == [
        "Developer implementation tests failed."
    ]


def test_development_gate_rejects_missing_implementation_results() -> None:
    result = evaluate_development_gate(
        {
            "last_result": {
                "implementation_blocked": False,
                "implementation_test_failed": False,
                "implementation_results": [],
            }
        }
    )

    assert result.ready is False
    assert result.reasons == [
        "Developer has no implementation results."
    ]


def test_development_gate_rejects_persisted_failing_test() -> None:
    result = evaluate_development_gate(
        {
            "last_result": {
                "implementation_blocked": False,
                "implementation_test_failed": False,
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
            }
        }
    )

    assert result.ready is False
    assert result.reasons == [
        "Developer contains failing test results."
    ]
