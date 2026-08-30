from ai_factory.agent_result import AgentImplementationRequest
from ai_factory.implementation_request import (
    ImplementationTask,
    build_implementation_tasks,
)


def test_build_implementation_tasks() -> None:
    requests = [
        AgentImplementationRequest(
            id="US-001",
            title="Passenger authentication",
            purpose="Implement authentication with automated tests.",
        ),
        AgentImplementationRequest(
            id="US-002",
            title="Ride request workflow",
            purpose="Implement ride creation and status handling.",
        ),
    ]

    tasks = build_implementation_tasks(
        agent_name="developer",
        requests=requests,
    )

    assert len(tasks) == 2

    assert isinstance(
        tasks[0],
        ImplementationTask,
    )

    assert tasks[0].agent_name == "developer"
    assert tasks[0].id == "US-001"
    assert tasks[0].title == "Passenger authentication"
    assert (
        tasks[0].purpose
        == "Implement authentication with automated tests."
    )

    assert tasks[1].id == "US-002"
    assert tasks[1].title == "Ride request workflow"


def test_build_implementation_tasks_returns_empty_list() -> None:
    tasks = build_implementation_tasks(
        agent_name="developer",
        requests=[],
    )

    assert tasks == []
