from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.devops_prompt import (
    build_devops_prompt,
)
from ai_factory.devops_result import (
    DevOpsResult,
)
from ai_factory.providers import (
    DevOpsProvider,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
    run_test_command,
)


@dataclass
class DevOpsExecution:
    """Result of one DevOps validation execution."""

    result: DevOpsResult
    prompt: str
    test_results: list[CommandExecutionResult]

    @property
    def passed(self) -> bool:
        return (
            self.result.passed
            and self.result.deployment_ready
            and all(
                test_result.passed
                for test_result in self.test_results
            )
            and not self.result.blockers
        )


def run_devops_validation(
    project_root: Path,
    context: dict[str, Any],
    provider: DevOpsProvider,
) -> DevOpsExecution:
    """Execute independent DevOps validation."""

    prompt = build_devops_prompt(
        context
    )

    result = provider.validate_devops(
        prompt
    )

    test_results = [
        run_test_command(
            project_root=project_root,
            command=command,
        )
        for command in result.test_commands
    ]

    return DevOpsExecution(
        result=result,
        prompt=prompt,
        test_results=test_results,
    )
