import pytest

from ai_factory.implementation_retry import (
    build_implementation_retry_context,
)


def test_build_implementation_retry_context() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "failed_task_id": "US-002",
                    "implementation_requests": [
                        {
                            "id": "US-001",
                            "title": "Authentication",
                            "purpose": "Implement authentication.",
                        },
                        {
                            "id": "US-002",
                            "title": "Ride creation",
                            "purpose": "Implement ride creation.",
                        },
                    ],
                    "test_results": [
                        {
                            "command": (
                                "python -m pytest "
                                "tests/test_auth.py -q"
                            ),
                            "returncode": 0,
                            "passed": True,
                            "stdout": "1 passed",
                            "stderr": "",
                        },
                        {
                            "command": (
                                "python -m pytest "
                                "tests/test_rides.py -q"
                            ),
                            "returncode": 1,
                            "passed": False,
                            "stdout": "1 failed",
                            "stderr": "AssertionError",
                        },
                    ],
                },
            }
        }
    }

    retry_context = build_implementation_retry_context(
        state
    )

    assert retry_context.task.id == "US-002"
    assert retry_context.task.title == "Ride creation"
    assert (
        retry_context.task.purpose
        == "Implement ride creation."
    )

    assert retry_context.test_results == [
        {
            "command": (
                "python -m pytest "
                "tests/test_rides.py -q"
            ),
            "returncode": 1,
            "passed": False,
            "stdout": "1 failed",
            "stderr": "AssertionError",
        }
    ]


def test_build_implementation_retry_context_rejects_missing_failed_task() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "implementation_requests": [],
                    "test_results": [],
                },
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="failed implementation task",
    ):
        build_implementation_retry_context(
            state
        )


def test_build_implementation_retry_context_rejects_unknown_failed_task() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "failed_task_id": "US-999",
                    "implementation_requests": [
                        {
                            "id": "US-001",
                            "title": "Authentication",
                            "purpose": "Implement authentication.",
                        }
                    ],
                    "test_results": [],
                },
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="Failed implementation task not found",
    ):
        build_implementation_retry_context(
            state
        )
