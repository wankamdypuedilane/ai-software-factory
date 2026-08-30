from dataclasses import dataclass
from typing import Any


@dataclass
class QAGateEvaluation:
    ready: bool
    reasons: list[str]


def evaluate_qa_gate(
    qa_state: dict[str, Any],
) -> QAGateEvaluation:
    """Evaluate whether QA is ready for human review."""

    reasons: list[str] = []

    if qa_state.get("status") != "REVIEW_REQUIRED":
        reasons.append(
            "QA is not ready for review."
        )

    last_result = qa_state.get(
        "last_result"
    )

    if not isinstance(last_result, dict):
        reasons.append(
            "QA result is missing."
        )

        return QAGateEvaluation(
            ready=False,
            reasons=reasons,
        )

    if last_result.get("qa_blockers"):
        reasons.append(
            "QA has unresolved blockers."
        )

    if last_result.get("qa_passed") is not True:
        reasons.append(
            "QA validation did not pass."
        )

    test_results = last_result.get(
        "qa_test_results",
        [],
    )

    if (
        isinstance(test_results, list)
        and any(
            isinstance(item, dict)
            and item.get("passed") is False
            for item in test_results
        )
    ):
        reasons.append(
            "QA tests failed."
        )

    defects = last_result.get(
        "qa_defects",
        [],
    )

    if isinstance(defects, list):
        blocking_severities = {
            "Critical",
            "High",
        }

        if any(
            isinstance(defect, dict)
            and defect.get("severity")
            in blocking_severities
            for defect in defects
        ):
            reasons.append(
                "QA has unresolved Critical or High severity defects."
            )

    return QAGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
