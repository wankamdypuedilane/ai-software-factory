"""What the engine actually observed about operational readiness.

SRE is the most structured agent in the Factory, and that made it the most
misleading. Its execution rule already required `observability_ready` and
`incident_readiness`, and its gate required both again plus a
findings-severity policy. It reads like the strictest boundary in the
workflow.

Every one of those requirements is a boolean the agent declares about itself.
`SREExecution.passed` was `result.passed and result.observability_ready and
result.incident_readiness and all(test_results) and not blockers`, and with no
executed command `all([])` is True, so the decision reduced to three model
booleans - immediately before the SRE Gate, which is the last engine-derived
barrier in front of the Production Gate.

Both readiness requirements are kept here rather than replaced, the findings
policy is applied at execution as well as at the gate, and the missing piece
is added: at least one command the engine ran.

The limits are worth stating. Nothing in the Factory observes a dashboard, an
alert rule, an on-call rotation or a runbook. `observability_ready` and
`incident_readiness` are assertions, and finding severities and statuses are
assertions too. What the engine verifies is that operational checks were
executed, what they returned, and that the declared requirements are applied
without the agent being able to skip them.
"""

from dataclasses import dataclass
from typing import Any

from ai_factory.blocker_contract import (
    blocking_blockers,
    coerce_blockers,
)


# The severities the SRE Gate already treats as blocking.
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
class SREEvidence:
    """What the engine can check, from structured fields only."""

    executed_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    blocking_blockers: int = 0
    unresolved_findings: int = 0
    observability_declared: bool = False
    incident_readiness_declared: bool = False


def _field(
    item: Any,
    name: str,
) -> Any:
    if isinstance(item, dict):
        return item.get(name)

    return getattr(item, name, None)


def _blocks(
    finding: Any,
) -> bool:
    severity = _field(finding, "severity")
    status = _field(finding, "status")

    if severity not in BLOCKING_FINDING_SEVERITIES:
        return False

    return status != RESOLVED_FINDING_STATUS


def describe_sre_evidence(
    test_results: list[Any] | None,
    blockers: list[Any] | None = None,
    findings: list[Any] | None = None,
    observability_ready: Any = None,
    incident_readiness: Any = None,
) -> SREEvidence:
    """Summarize SRE evidence from live objects or persisted state alike.

    Both shapes are accepted so a decision taken during execution and the
    same decision taken later from `state.yaml` cannot diverge.
    """

    executed = 0
    passed = 0
    failed = 0

    for item in test_results or []:
        outcome = _field(item, "passed")

        if not isinstance(outcome, bool):
            continue

        executed += 1

        if outcome:
            passed += 1
        else:
            failed += 1

    return SREEvidence(
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
        observability_declared=observability_ready is True,
        incident_readiness_declared=incident_readiness is True,
    )


def sre_evidence_satisfied(
    evidence: SREEvidence,
) -> bool:
    """Whether every capability the gate claims is ready is supported."""

    return (
        evidence.executed_checks >= 1
        and evidence.failed_checks == 0
        and evidence.blocking_blockers == 0
        and evidence.unresolved_findings == 0
        and evidence.observability_declared
        and evidence.incident_readiness_declared
    )


def sre_evidence_reasons(
    evidence: SREEvidence,
) -> list[str]:
    """Explain, deterministically, why SRE is not ready.

    The existing gate wording is preserved so that an operator reading a
    reason list sees the same sentences for the same conditions.
    """

    reasons: list[str] = []

    if evidence.blocking_blockers:
        reasons.append(
            "SRE has unresolved blockers."
        )

    if not evidence.observability_declared:
        reasons.append(
            "Observability is not ready."
        )

    if not evidence.incident_readiness_declared:
        reasons.append(
            "Incident readiness is not sufficient."
        )

    if evidence.executed_checks < 1:
        reasons.append(
            "SRE produced no executed validation evidence."
        )

    if evidence.failed_checks:
        reasons.append(
            "SRE tests failed."
        )

    if evidence.unresolved_findings:
        reasons.append(
            "SRE has unresolved Critical or High severity findings."
        )

    return reasons


def missing_sre_evidence(
    result: Any,
) -> str:
    """Return why an SRE response declares no executable work, or "".

    Reported rather than raised. The published schema declares `passed`,
    `observability_ready`, `incident_readiness` and `test_commands`
    independently and cannot express a rule tying them together, so a
    response combining them is one the Factory said was allowed. Refusing it
    fatally would repeat the round-11 defect; the engine simply does not
    grant success without evidence.
    """

    commands = getattr(result, "test_commands", None)

    if isinstance(commands, list) and any(
        isinstance(command, str) and command.strip()
        for command in commands
    ):
        return ""

    return (
        "The SRE response declares no validation command, so the Factory "
        "has nothing to execute and operational readiness cannot be "
        "confirmed."
    )
