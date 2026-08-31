from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.providers import (
    SecurityProvider,
)
from ai_factory.security_prompt import (
    build_security_prompt,
)
from ai_factory.security_result import (
    SecurityResult,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
    run_test_command,
)


@dataclass
class SecurityExecution:
    """Result of one security validation execution."""

    result: SecurityResult
    prompt: str
    test_results: list[CommandExecutionResult]

    @property
    def passed(self) -> bool:
        return (
            self.result.passed
            and all(
                test_result.passed
                for test_result in self.test_results
            )
            and not self.result.blockers
        )


def run_security_validation(
    project_root: Path,
    context: dict[str, Any],
    provider: SecurityProvider,
) -> SecurityExecution:
    """Execute independent security validation."""

    prompt = build_security_prompt(
        context
    )

    result = provider.validate_security(
        prompt
    )

    test_results = [
        run_test_command(
            project_root=project_root,
            command=command,
        )
        for command in result.test_commands
    ]

    return SecurityExecution(
        result=result,
        prompt=prompt,
        test_results=test_results,
    )
