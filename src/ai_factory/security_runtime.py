from ai_factory.test_command_policy import allowed_test_commands
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.providers import (
    SecurityProvider,
)
from ai_factory.security_evidence import (
    SecurityEvidence,
    describe_security_evidence,
    security_evidence_satisfied,
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
    def evidence(self) -> SecurityEvidence:
        """What the engine observed, independently of what was claimed."""

        return describe_security_evidence(
            test_results=self.test_results,
            blockers=self.result.blockers,
            findings=self.result.findings,
        )

    @property
    def passed(self) -> bool:
        """Whether security passed, decided by executed evidence.

        `result.passed` can no longer carry this alone: with no executed
        check there is nothing to be right about. It is kept as a veto, so
        an agent reporting a problem is still believed even when every
        command it ran was green - withholding success is safe, and the
        reason belongs in its findings or blockers.
        """

        return (
            security_evidence_satisfied(self.evidence)
            and self.result.passed
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
        for command in allowed_test_commands(list(result.test_commands))
    ]

    return SecurityExecution(
        result=result,
        prompt=prompt,
        test_results=test_results,
    )
