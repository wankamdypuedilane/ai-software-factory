from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.implementation_provider import (
    ImplementationProvider,
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


@dataclass
class ImplementationBatchResult:
    results: list[ImplementationResult] = field(
        default_factory=list
    )
    written_files: list[Path] = field(
        default_factory=list
    )
    blocked: bool = False


def run_implementation_batch(
    project_root: Path,
    agent_name: str,
    agent_result: AgentResult,
    context: dict[str, Any],
    provider: ImplementationProvider,
) -> ImplementationBatchResult:
    """Execute implementation requests sequentially."""

    tasks = build_implementation_tasks(
        agent_name=agent_name,
        requests=agent_result.implementation_requests,
    )

    batch = ImplementationBatchResult()

    for task in tasks:
        result, written_files = run_implementation_task(
            project_root=project_root,
            task=task,
            context=context,
            provider=provider,
        )

        batch.results.append(
            result
        )

        batch.written_files.extend(
            written_files
        )

        if result.blockers:
            batch.blocked = True
            break

    return batch
