"""What the engine actually observed about QA.

`QAExecution.passed` used to be `result.passed and all(test_results) and not
blockers`. With no executed check, `all([])` is True and the decision reduced
to `result.passed` - the QA agent's own verdict on its own work - which then
became `qa_passed`, opened the QA Gate, and put Security one human signature
away from a claim nothing had verified.

QA may propose a test plan, commands, defects and blockers. Whether QA passed
is derived here, from what ran.

Authority is deliberately one-directional. The engine's evidence is necessary
for success and the agent's claim can never supply it, but an agent reporting
failure is still believed: withholding success is safe, granting it is not.
"""

from dataclasses import dataclass
from typing import Any

from ai_factory.blocker_contract import (
    blocking_blockers,
    coerce_blockers,
)


# The severities the QA Gate already treats as unresolved impediments.
BLOCKING_DEFECT_SEVERITIES = frozenset(
    {
        "Critical",
        "High",
    }
)


@dataclass(frozen=True)
class QAEvidence:
    """Counts the engine can verify, from structured fields only."""

    executed_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    blocking_blockers: int = 0
    blocking_defects: int = 0


def _passed_flag(
    item: Any,
) -> bool | None:
    """Read an execution outcome from a result object or a persisted dict."""

    if isinstance(item, dict):
        value = item.get("passed")

        return value if isinstance(value, bool) else None

    value = getattr(item, "passed", None)

    return value if isinstance(value, bool) else None


def _severity(
    defect: Any,
) -> str:
    if isinstance(defect, dict):
        value = defect.get("severity")
    else:
        value = getattr(defect, "severity", None)

    return value if isinstance(value, str) else ""


def describe_qa_evidence(
    test_results: list[Any] | None,
    blockers: list[Any] | None = None,
    defects: list[Any] | None = None,
) -> QAEvidence:
    """Summarize QA evidence from live objects or persisted state alike.

    Both shapes are accepted so that a decision made during execution and the
    same decision made later from `state.yaml` cannot diverge.
    """

    executed = 0
    passed = 0
    failed = 0

    for item in test_results or []:
        outcome = _passed_flag(item)

        if outcome is None:
            continue

        executed += 1

        if outcome:
            passed += 1
        else:
            failed += 1

    return QAEvidence(
        executed_checks=executed,
        passed_checks=passed,
        failed_checks=failed,
        blocking_blockers=len(
            blocking_blockers(
                coerce_blockers(blockers or [])
            )
        ),
        blocking_defects=len(
            [
                defect
                for defect in (defects or [])
                if _severity(defect) in BLOCKING_DEFECT_SEVERITIES
            ]
        ),
    )


def qa_evidence_satisfied(
    evidence: QAEvidence,
) -> bool:
    """Whether what the engine observed is enough to call QA successful."""

    return (
        evidence.executed_checks >= 1
        and evidence.failed_checks == 0
        and evidence.blocking_blockers == 0
        and evidence.blocking_defects == 0
    )


def qa_evidence_reasons(
    evidence: QAEvidence,
) -> list[str]:
    """Explain, deterministically, why the evidence is not sufficient."""

    reasons: list[str] = []

    if evidence.executed_checks < 1:
        reasons.append(
            "QA produced no executed validation evidence."
        )

    if evidence.failed_checks:
        reasons.append(
            "QA tests failed."
        )

    if evidence.blocking_blockers:
        reasons.append(
            "QA has unresolved blockers."
        )

    if evidence.blocking_defects:
        reasons.append(
            "QA has unresolved Critical or High severity defects."
        )

    return reasons


def missing_qa_evidence(
    result: Any,
) -> str:
    """Return why a QA response declares no validation work, or "".

    Reported rather than raised. The published QA schema declares `passed`
    and `test_commands` independently and cannot express a rule tying them
    together, so a response combining them is one the Factory said was
    allowed. Refusing it fatally would repeat a defect already corrected in
    the blocker contract; the engine simply does not grant success without
    evidence.
    """

    commands = getattr(result, "test_commands", None)

    if isinstance(commands, list) and any(
        isinstance(command, str) and command.strip()
        for command in commands
    ):
        return ""

    return (
        "The QA response declares no validation command, so the Factory has "
        "nothing to execute and QA cannot be reported as passed."
    )
