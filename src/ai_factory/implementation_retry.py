from dataclasses import dataclass
from typing import Any

from ai_factory.agent_result import (
    AgentImplementationRequest,
)


@dataclass
class ImplementationRetryContext:
    task: AgentImplementationRequest
    test_results: list[dict[str, Any]]


def build_implementation_retry_context(
    state: dict[str, Any],
) -> ImplementationRetryContext:
    """Build retry context for the failed Developer implementation task."""

    agents = state.get("agents", {})

    developer = agents.get("developer")

    if not isinstance(developer, dict):
        raise ValueError(
            "Project state does not contain a valid developer agent."
        )

    last_result = developer.get("last_result")

    if not isinstance(last_result, dict):
        raise ValueError(
            "Developer does not contain a persisted result."
        )

    failed_task_id = last_result.get(
        "failed_task_id"
    )

    if not isinstance(failed_task_id, str) or not failed_task_id.strip():
        raise ValueError(
            "Developer does not contain a failed implementation task."
        )

    requests = last_result.get(
        "implementation_requests",
        [],
    )

    if not isinstance(requests, list):
        raise ValueError(
            "Developer implementation_requests must be a list."
        )

    failed_request = None

    for request in requests:
        if not isinstance(request, dict):
            continue

        if request.get("id") == failed_task_id:
            failed_request = request
            break

    if failed_request is None:
        raise ValueError(
            f"Failed implementation task not found: {failed_task_id}"
        )

    title = failed_request.get("title")
    purpose = failed_request.get("purpose")

    if not isinstance(title, str) or not title.strip():
        raise ValueError(
            "Failed implementation task title is required."
        )

    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError(
            "Failed implementation task purpose is required."
        )

    test_results = last_result.get(
        "test_results",
        [],
    )

    if not isinstance(test_results, list):
        raise ValueError(
            "Developer test_results must be a list."
        )

    failed_test_results = [
        result
        for result in test_results
        if isinstance(result, dict)
        and result.get("passed") is False
    ]

    return ImplementationRetryContext(
        task=AgentImplementationRequest(
            id=failed_task_id,
            title=title,
            purpose=purpose,
        ),
        test_results=failed_test_results,
    )
