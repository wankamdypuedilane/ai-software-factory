from dataclasses import dataclass, field
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
from ai_factory.test_runner import (
    CommandExecutionResult,
    run_test_command,
)


@dataclass
class ImplementationExecution:
    result: ImplementationResult
    written_files: list[Path] = field(
        default_factory=list
    )
    test_results: list[CommandExecutionResult] = field(
        default_factory=list
    )

    @property
    def tests_passed(self) -> bool:
        return all(
            test_result.passed
            for test_result in self.test_results
        )


def run_implementation_task(
    project_root: Path,
    task: ImplementationTask,
    context: dict[str, Any],
    provider: ImplementationProvider,
) -> ImplementationExecution:
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
        return ImplementationExecution(
            result=result,
        )

    written_files = apply_implementation_result(
        project_root=project_root,
        result=result,
    )

    test_results = [
        run_test_command(
            project_root=project_root,
            command=command,
        )
        for command in result.tests
    ]

    return ImplementationExecution(
        result=result,
        written_files=written_files,
        test_results=test_results,
    )
