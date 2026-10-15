from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.providers import QAProvider
from ai_factory.qa_evidence import (
    QAEvidence,
    describe_qa_evidence,
    qa_evidence_satisfied,
)
from ai_factory.qa_prompt import build_qa_prompt
from ai_factory.qa_result import QAResult
from ai_factory.test_runner import (
    CommandExecutionResult,
    run_test_command,
)


@dataclass
class QAExecution:
    """Result of one QA validation execution."""

    result: QAResult
    prompt: str
    test_results: list[CommandExecutionResult]

    @property
    def evidence(self) -> QAEvidence:
        """What the engine observed, independently of what QA claimed."""

        return describe_qa_evidence(
            test_results=self.test_results,
            blockers=self.result.blockers,
            defects=self.result.defects,
        )

    @property
    def passed(self) -> bool:
        """Whether QA succeeded, decided by executed evidence.

        `result.passed` is no longer able to carry this on its own: without
        an executed check there is nothing to be right about. It is kept as a
        veto, so an agent reporting failure is still believed even when every
        command it ran was green - withholding success is safe, and the
        reason it withheld belongs in its defects or blockers.
        """

        return (
            qa_evidence_satisfied(self.evidence)
            and self.result.passed
        )


def run_qa_validation(
    project_root: Path,
    context: dict[str, Any],
    provider: QAProvider,
) -> QAExecution:
    """Run one independent QA validation."""

    prompt = build_qa_prompt(
        context
    )

    result = provider.validate_qa(
        prompt
    )

    test_results = [
        run_test_command(
            project_root=project_root,
            command=command,
        )
        for command in result.test_commands
    ]

    return QAExecution(
        result=result,
        prompt=prompt,
        test_results=test_results,
    )
