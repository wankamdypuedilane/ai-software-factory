"""What the engine actually observed about security.

`SecurityExecution.passed` used to be `result.passed and all(test_results)
and not blockers`. With no executed check, `all([])` is True and the decision
reduced to `result.passed` - the Security agent's own verdict on its own
review - which became `security_passed`, opened the Security Gate, and put
DevOps one human signature away from a claim nothing had verified.

Security may propose checks, findings, severities and remediations. Whether
the security phase passed is derived here, from what ran.

The limits of that are worth stating plainly. Severity and status are
declared by the agent: nothing in the Factory can independently establish
that a vulnerability is Critical rather than Low, or that a finding has
truly been resolved. What the engine can verify is that checks were executed
and what they returned, and that the declared policy is applied to the
declared values without the agent being able to skip it. Everything else
remains an assertion, and is documented as one.
"""

from dataclasses import dataclass
from typing import Any

from ai_factory.blocker_contract import (
    blocking_blockers,
    coerce_blockers,
)


# The severities the Security Gate already treats as blocking.
BLOCKING_FINDING_SEVERITIES = frozenset(
    {
        "Critical",
        "High",
    }
)

# The one status that clears a blocking finding. Compared exactly, as a
# declared enumeration value - never matched as prose.
RESOLVED_FINDING_STATUS = "RESOLVED"


@dataclass(frozen=True)
class SecurityEvidence:
    """Counts the engine can verify, from structured fields only."""

    executed_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    blocking_blockers: int = 0
    unresolved_findings: int = 0


def _field(
    item: Any,
    name: str,
) -> Any:
    if isinstance(item, dict):
        return item.get(name)

    return getattr(item, name, None)


def _passed_flag(
    item: Any,
) -> bool | None:
    value = _field(item, "passed")

    return value if isinstance(value, bool) else None


def _blocks(
    finding: Any,
) -> bool:
    severity = _field(finding, "severity")
    status = _field(finding, "status")

    if severity not in BLOCKING_FINDING_SEVERITIES:
        return False

    return status != RESOLVED_FINDING_STATUS


def describe_security_evidence(
    test_results: list[Any] | None,
    blockers: list[Any] | None = None,
    findings: list[Any] | None = None,
) -> SecurityEvidence:
    """Summarize security evidence from live objects or persisted state.

    Both shapes are accepted so a decision taken during execution and the
    same decision taken later from `state.yaml` cannot diverge.
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

    return SecurityEvidence(
        executed_checks=executed,
        passed_checks=passed,
        failed_checks=failed,
        blocking_blockers=len(
            blocking_blockers(
                coerce_blockers(blockers or [])
            )
        ),
        unresolved_findings=len(
            [
                finding
                for finding in (findings or [])
                if _blocks(finding)
            ]
        ),
    )


def security_evidence_satisfied(
    evidence: SecurityEvidence,
) -> bool:
    """Whether what the engine observed is enough to call security passed."""

    return (
        evidence.executed_checks >= 1
        and evidence.failed_checks == 0
        and evidence.blocking_blockers == 0
        and evidence.unresolved_findings == 0
    )


def security_evidence_reasons(
    evidence: SecurityEvidence,
) -> list[str]:
    """Explain, deterministically, why the evidence is not sufficient."""

    reasons: list[str] = []

    if evidence.executed_checks < 1:
        reasons.append(
            "Security produced no executed validation evidence."
        )

    if evidence.failed_checks:
        reasons.append(
            "Security tests failed."
        )

    if evidence.blocking_blockers:
        reasons.append(
            "Security has unresolved blockers."
        )

    if evidence.unresolved_findings:
        reasons.append(
            "Security has unresolved Critical or High severity findings."
        )

    return reasons


def missing_security_evidence(
    result: Any,
) -> str:
    """Return why a security response declares no work, or "".

    Reported rather than raised. The published schema declares `passed` and
    `test_commands` independently and cannot express a rule tying them
    together, so a response combining them is one the Factory said was
    allowed. Refusing it fatally would repeat the round-11 defect; the
    engine simply does not grant success without evidence.
    """

    commands = getattr(result, "test_commands", None)

    if isinstance(commands, list) and any(
        isinstance(command, str) and command.strip()
        for command in commands
    ):
        return ""

    return (
        "The security response declares no validation command, so the "
        "Factory has nothing to execute and security cannot be reported "
        "as passed."
    )
