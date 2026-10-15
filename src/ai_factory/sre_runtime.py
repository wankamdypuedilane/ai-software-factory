from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.providers import (
    SREProvider,
)
from ai_factory.sre_evidence import (
    SREEvidence,
    describe_sre_evidence,
    sre_evidence_satisfied,
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
    def evidence(self) -> SREEvidence:
        """What the engine observed, independently of what was claimed."""

        return describe_sre_evidence(
            test_results=self.test_results,
            blockers=self.result.blockers,
            findings=self.result.findings,
            observability_ready=self.result.observability_ready,
            incident_readiness=self.result.incident_readiness,
        )

    @property
    def passed(self) -> bool:
        """Whether SRE succeeded, decided by observable requirements.

        Both declared readiness flags are still required - nothing is
        relaxed - the findings policy the gate applies is applied here too,
        and an executed check is now required with them. `result.passed` is
        kept as a veto: an agent reporting a problem is still believed, but
        it can no longer certify production readiness on its own.
        """

        return (
            sre_evidence_satisfied(self.evidence)
            and self.result.passed
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
