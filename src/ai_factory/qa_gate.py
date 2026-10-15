from ai_factory.qa_evidence import (
    describe_qa_evidence,
    qa_evidence_reasons,
    qa_evidence_satisfied,
)
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

    test_results = last_result.get(
        "qa_test_results",
        [],
    )

    defects = last_result.get(
        "qa_defects",
        [],
    )

    # Re-derived from the persisted evidence rather than trusted from the
    # stored `qa_passed` flag. The runtime already decides the same way, so
    # this changes nothing for a state this engine wrote - and it refuses a
    # state written by an older engine, restored, or edited by hand, where
    # the flag could assert a success no executed check supports.
    evidence = describe_qa_evidence(
        test_results=test_results if isinstance(test_results, list) else [],
        blockers=last_result.get("qa_blockers", []),
        defects=defects if isinstance(defects, list) else [],
    )

    reasons.extend(
        qa_evidence_reasons(evidence)
    )

    # The agent keeps its veto: it may report failure over green checks, and
    # the gate honours that. It may not open the gate on its own.
    if (
        qa_evidence_satisfied(evidence)
        and last_result.get("qa_passed") is not True
    ):
        reasons.append(
            "QA validation did not pass."
        )

    return QAGateEvaluation(
        ready=not reasons,
        reasons=reasons,
    )
