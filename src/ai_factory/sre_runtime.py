from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.providers import (
    SREProvider,
)
from ai_factory.sre_prompt import (
    build_sre_prompt,
)
from ai_factory.sre_result import (
    SREResult,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
    run_test_command,
)


@dataclass
class SREExecution:
    """Result of one SRE validation execution."""

    result: SREResult
    prompt: str
    test_results: list[CommandExecutionResult]

    @property
    def passed(self) -> bool:
        return (
            self.result.passed
            and self.result.observability_ready
            and self.result.incident_readiness
            and all(
                test_result.passed
                for test_result in self.test_results
            )
            and not self.result.blockers
        )


def run_sre_validation(
    project_root: Path,
    context: dict[str, Any],
    provider: SREProvider,
) -> SREExecution:
    """Execute independent SRE validation."""

    prompt = build_sre_prompt(
        context
    )

    result = provider.validate_sre(
        prompt
    )

    test_results = [
        run_test_command(
            project_root=project_root,
            command=command,
        )
        for command in result.test_commands
    ]

    return SREExecution(
        result=result,
        prompt=prompt,
        test_results=test_results,
    )
