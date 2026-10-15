"""What the engine actually observed about deployment readiness.

DevOps is not shaped like QA or Security, and the difference is worth being
precise about. Its gate already refused an empty `rollback_strategy` and a
`deployment_ready` that was not True, which makes it look stricter than the
others. It was not: both of those are declared by the agent. The extra
checks raise what the agent must *say*, not what the engine *observes*.

Underneath, the same collapse was present. `DevOpsExecution.passed` was
`result.passed and result.deployment_ready and all(test_results) and not
blockers`, and with no executed command `all([])` is True, leaving the
decision to two model booleans and a non-empty string.

Both existing requirements are kept here rather than replaced - a unit that
declares no rollback still fails, exactly as before - and the missing one is
added: at least one command the engine ran.

The limits are worth stating. `deployment_ready` is an assertion; nothing in
the Factory observes a deployment. `rollback_strategy` is prose; the engine
can see that it is non-empty and nothing more. What the engine verifies is
that checks were executed, what they returned, and that the declared
requirements are applied without the agent being able to skip them.
"""

from dataclasses import dataclass
from typing import Any

from ai_factory.blocker_contract import (
    blocking_blockers,
    coerce_blockers,
)


@dataclass(frozen=True)
class DevOpsEvidence:
    """What the engine can check, from structured fields only."""

    executed_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    blocking_blockers: int = 0
    deployment_declared: bool = False
    rollback_declared: bool = False


def _passed_flag(
    item: Any,
) -> bool | None:
    if isinstance(item, dict):
        value = item.get("passed")
    else:
        value = getattr(item, "passed", None)

    return value if isinstance(value, bool) else None


def describe_devops_evidence(
    test_results: list[Any] | None,
    blockers: list[Any] | None = None,
    deployment_ready: Any = None,
    rollback_strategy: Any = None,
) -> DevOpsEvidence:
    """Summarize DevOps evidence from live objects or persisted state.

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

    return DevOpsEvidence(
        executed_checks=executed,
        passed_checks=passed,
        failed_checks=failed,
        blocking_blockers=len(
            blocking_blockers(
                coerce_blockers(blockers or [])
            )
        ),
        deployment_declared=deployment_ready is True,
        rollback_declared=(
            isinstance(rollback_strategy, str)
            and bool(rollback_strategy.strip())
        ),
    )


def devops_evidence_satisfied(
    evidence: DevOpsEvidence,
) -> bool:
    """Whether every capability the gate claims is ready is supported."""

    return (
        evidence.executed_checks >= 1
        and evidence.failed_checks == 0
        and evidence.blocking_blockers == 0
        and evidence.deployment_declared
        and evidence.rollback_declared
    )


def devops_evidence_reasons(
    evidence: DevOpsEvidence,
) -> list[str]:
    """Explain, deterministically, why DevOps is not ready.

    The existing gate wording is preserved so that an operator reading a
    reason list sees the same sentences for the same conditions.
    """

    reasons: list[str] = []

    if evidence.blocking_blockers:
        reasons.append(
            "DevOps has unresolved blockers."
        )

    if not evidence.deployment_declared:
        reasons.append(
            "Deployment is not ready."
        )

    if evidence.executed_checks < 1:
        reasons.append(
            "DevOps produced no executed validation evidence."
        )

    if evidence.failed_checks:
        reasons.append(
            "DevOps tests failed."
        )

    if not evidence.rollback_declared:
        reasons.append(
            "Rollback strategy is missing."
        )

    return reasons


def missing_devops_evidence(
    result: Any,
) -> str:
    """Return why a DevOps response declares no executable work, or "".

    Reported rather than raised. The published schema declares `passed`,
    `deployment_ready` and `test_commands` independently and cannot express
    a rule tying them together, so a response combining them is one the
    Factory said was allowed. Refusing it fatally would repeat the round-11
    defect; the engine simply does not grant success without evidence.
    """

    commands = getattr(result, "test_commands", None)

    if isinstance(commands, list) and any(
        isinstance(command, str) and command.strip()
        for command in commands
    ):
        return ""

    return (
        "The DevOps response declares no validation command, so the Factory "
        "has nothing to execute and deployment readiness cannot be "
        "confirmed."
    )
