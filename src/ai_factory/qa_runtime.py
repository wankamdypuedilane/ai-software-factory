from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.providers import QAProvider
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
