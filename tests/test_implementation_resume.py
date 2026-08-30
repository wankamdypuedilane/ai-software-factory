from ai_factory.agent_result import (
    AgentImplementationRequest,
)
from ai_factory.implementation_resume import (
    filter_pending_implementation_requests,
    get_completed_implementation_task_ids,
)


def test_get_completed_implementation_task_ids() -> None:
    state = {
        "agents": {
            "developer": {
                "last_result": {
                    "implementation_results": [
                        {
                            "task_id": "US-001",
                            "blockers": [],
                        },
                        {
                            "task_id": "US-002",
                            "blockers": [
                                "Requirement is ambiguous.",
                            ],
                        },
                        {
                            "task_id": "US-003",
                            "blockers": [],
                        },
                    ]
                }
            }
        }
    }

    completed = get_completed_implementation_task_ids(
        state
    )

    assert completed == {
        "US-001",
        "US-003",
    }


def test_get_completed_implementation_task_ids_returns_empty_set() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "READY",
            }
        }
    }

    completed = get_completed_implementation_task_ids(
        state
    )

    assert completed == set()


def test_filter_pending_implementation_requests() -> None:
    requests = [
        AgentImplementationRequest(
            id="US-001",
            title="Authentication",
            purpose="Implement authentication.",
        ),
        AgentImplementationRequest(
            id="US-002",
            title="Ride creation",
            purpose="Implement ride creation.",
        ),
        AgentImplementationRequest(
            id="US-003",
            title="Ride completion",
            purpose="Implement ride completion.",
        ),
    ]

    pending = filter_pending_implementation_requests(
        requests=requests,
        completed_task_ids={
            "US-001",
        },
    )

    assert [
        request.id
        for request in pending
    ] == [
        "US-002",
        "US-003",
    ]
