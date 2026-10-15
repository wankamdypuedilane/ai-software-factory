from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_factory.blocker_contract import (
    blocking_blockers,
)
from ai_factory.agent_result import (
    AgentImplementationRequest,
    AgentResult,
)
from ai_factory.implementation_provider import (
    ImplementationProvider,
)
from ai_factory.implementation_resume import (
    filter_pending_implementation_requests,
)
from ai_factory.implementation_request import (
    build_implementation_tasks,
)
from ai_factory.implementation_result import (
    ImplementationResult,
)
from ai_factory.implementation_runtime import (
    run_implementation_task,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
)


@dataclass
class ImplementationBatchResult:
    results: list[ImplementationResult] = field(
        default_factory=list
    )
    written_files: list[Path] = field(
        default_factory=list
    )
    test_results: list[CommandExecutionResult] = field(
        default_factory=list
    )
    blocked: bool = False
    test_failed: bool = False
    failed_task_id: str | None = None


def run_implementation_batch(
    project_root: Path,
    agent_name: str,
    agent_result: AgentResult,
    context: dict[str, Any],
    provider: ImplementationProvider,
    completed_task_ids: set[str] | None = None,
    retry_task_id: str | None = None,
    retry_task: AgentImplementationRequest | None = None,
    retry_test_results: list[dict[str, Any]] | None = None,
) -> ImplementationBatchResult:
    """Execute pending implementation requests sequentially."""

    completed_task_ids = (
        completed_task_ids
        if completed_task_ids is not None
        else set()
    )

    pending_requests = filter_pending_implementation_requests(
        requests=agent_result.implementation_requests,
        completed_task_ids=completed_task_ids,
    )

    if retry_task is not None:
        replacement_task_id = (
            pending_requests[0].id
            if pending_requests
            and not any(
                request.id == retry_task.id
                for request in pending_requests
            )
            else None
        )

        pending_requests = [
            request
            for request in pending_requests
            if request.id != retry_task.id
            and request.id != replacement_task_id
        ]

        pending_requests.insert(
            0,
            retry_task,
        )

        retry_task_id = retry_task.id

    tasks = build_implementation_tasks(
        agent_name=agent_name,
        requests=pending_requests,
    )

    batch = ImplementationBatchResult()

    for task in tasks:
        task_retry_results = None

        if (
            retry_task_id is not None
            and task.id == retry_task_id
        ):
            task_retry_results = retry_test_results

        execution = run_implementation_task(
            project_root=project_root,
            task=task,
            context=context,
            provider=provider,
            retry_test_results=task_retry_results,
        )

        result = execution.result

        batch.test_results.extend(
            execution.test_results
        )

        batch.results.append(
            result
        )

        # A blocked unit is blocked, not failed: it is classified first so
        # that fail-closed outcome semantics cannot relabel it.
        if blocking_blockers(result.blockers):
            batch.blocked = True
            break

        if not execution.execution_succeeded:
            batch.test_failed = True
            batch.failed_task_id = result.task_id
            break

        # Only a unit whose transaction was promoted contributes files:
        # a discarded transaction wrote nothing to the workspace.
        batch.written_files.extend(
            execution.written_files
        )

    return batch
