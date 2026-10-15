from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.devops_evidence import (
    DevOpsEvidence,
    describe_devops_evidence,
    devops_evidence_satisfied,
)
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
    def evidence(self) -> DevOpsEvidence:
        """What the engine observed, independently of what was claimed."""

        return describe_devops_evidence(
            test_results=self.test_results,
            blockers=self.result.blockers,
            deployment_ready=self.result.deployment_ready,
            rollback_strategy=self.result.rollback_strategy,
        )

    @property
    def passed(self) -> bool:
        """Whether DevOps succeeded, decided by observable requirements.

        The declared deployment flag and rollback strategy are still
        required - nothing is relaxed - and an executed check is now
        required with them. `result.passed` is kept as a veto: an agent
        reporting a problem is still believed, but it can no longer grant
        success on its own.
        """

        return (
            devops_evidence_satisfied(self.evidence)
            and self.result.passed
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
