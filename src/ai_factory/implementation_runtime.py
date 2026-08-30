from pathlib import Path
from typing import Any

from ai_factory.implementation_pipeline import (
    apply_implementation_result,
)
from ai_factory.implementation_prompt import (
    build_implementation_prompt,
)
from ai_factory.implementation_provider import (
    ImplementationProvider,
)
from ai_factory.implementation_request import (
    ImplementationTask,
)
from ai_factory.implementation_result import (
    ImplementationResult,
)


def run_implementation_task(
    project_root: Path,
    task: ImplementationTask,
    context: dict[str, Any],
    provider: ImplementationProvider,
) -> tuple[ImplementationResult, list[Path]]:
    """Execute and apply one focused implementation task."""

    prompt = build_implementation_prompt(
        task=task,
        context=context,
    )

    result = provider.implement(
        prompt
    )

    if result.task_id != task.id:
        raise ValueError(
            "Implementation result task ID does not match "
            f"the requested task: {result.task_id} != {task.id}"
        )

    if result.blockers:
        return result, []

    written_files = apply_implementation_result(
        project_root=project_root,
        result=result,
    )

    return result, written_files
