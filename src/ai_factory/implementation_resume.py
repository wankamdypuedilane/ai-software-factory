from typing import Any

from ai_factory.agent_result import (
    AgentImplementationRequest,
)


def get_completed_implementation_task_ids(
    state: dict[str, Any],
) -> set[str]:
    """Return successfully completed Developer task IDs."""

    agents = state.get("agents", {})

    developer = agents.get(
        "developer",
        {},
    )

    if not isinstance(developer, dict):
        return set()

    last_result = developer.get(
        "last_result",
        {},
    )

    if not isinstance(last_result, dict):
        return set()

    results = last_result.get(
        "implementation_results",
        [],
    )

    if not isinstance(results, list):
        return set()

    completed: set[str] = set()

    for result in results:
        if not isinstance(result, dict):
            continue

        task_id = result.get("task_id")
        blockers = result.get(
            "blockers",
            [],
        )

        if (
            isinstance(task_id, str)
            and task_id.strip()
            and isinstance(blockers, list)
            and not blockers
        ):
            completed.add(
                task_id
            )

    return completed


def filter_pending_implementation_requests(
    requests: list[AgentImplementationRequest],
    completed_task_ids: set[str],
) -> list[AgentImplementationRequest]:
    """Return implementation requests that still need execution."""

    return [
        request
        for request in requests
        if request.id not in completed_task_ids
    ]
