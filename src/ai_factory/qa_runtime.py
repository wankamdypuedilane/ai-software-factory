from dataclasses import dataclass
from typing import Any

from ai_factory.providers import QAProvider
from ai_factory.qa_prompt import build_qa_prompt
from ai_factory.qa_result import QAResult


@dataclass
class QAExecution:
    """Result of one QA validation execution."""

    result: QAResult
    prompt: str


def run_qa_validation(
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

    return QAExecution(
        result=result,
        prompt=prompt,
    )
