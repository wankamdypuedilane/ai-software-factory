"""Structured blockers.

A blocker changes what the Factory is allowed to do, so it must satisfy a
contract the Factory can verify. Declaring that a decision needs a human is
not an impediment to the work: it is a question. Only a real external
dependency the agent cannot resolve may block a gate or an agent.
"""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class BlockerKind(str, Enum):
    """Why the agent reported the impediment."""

    EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY"
    HUMAN_DECISION = "HUMAN_DECISION"
    LOCAL_DEFECT = "LOCAL_DEFECT"
    INFORMATION = "INFORMATION"


class BlockerScope(str, Enum):
    """Where the impediment lives."""

    EXTERNAL = "EXTERNAL"
    PROJECT = "PROJECT"
    WORKSPACE = "WORKSPACE"


BLOCKER_KIND_VALUES = tuple(kind.value for kind in BlockerKind)
BLOCKER_SCOPE_VALUES = tuple(scope.value for scope in BlockerScope)


@dataclass(frozen=True)
class Blocker:
    message: str
    kind: BlockerKind = BlockerKind.EXTERNAL_DEPENDENCY
    scope: BlockerScope = BlockerScope.EXTERNAL
    fixable_by_agent: bool = False
    requires_human_input: bool = False
    blocking: bool = True


def is_effectively_blocking(
    blocker: Blocker,
) -> bool:
    """Return whether a blocker is allowed to stop the workflow.

    The three conditions are checked by the Factory, never asserted by the
    agent alone: it must be an external dependency, it must claim to block,
    and the agent must not be able to fix it itself.
    """

    return (
        blocker.kind is BlockerKind.EXTERNAL_DEPENDENCY
        and blocker.blocking
        and not blocker.fixable_by_agent
    )


def blocking_blockers(
    blockers: list[Blocker],
) -> list[Blocker]:
    """Return only the blockers entitled to stop the workflow."""

    return [
        blocker
        for blocker in blockers
        if is_effectively_blocking(blocker)
    ]


def normalize_blockers(
    blockers: list[Blocker],
) -> tuple[list[Blocker], list[str]]:
    """Demote everything that is not a real impediment.

    A demoted blocker is not discarded: when it asks for a human decision
    its message is surfaced as a question, which is the channel that can
    actually be answered.
    """

    normalized: list[Blocker] = []
    questions: list[str] = []

    for blocker in blockers:
        if is_effectively_blocking(blocker):
            normalized.append(blocker)
            continue

        demoted = replace(
            blocker,
            blocking=False,
        )

        normalized.append(demoted)

        if (
            demoted.kind is BlockerKind.HUMAN_DECISION
            or demoted.requires_human_input
        ):
            questions.append(demoted.message)

    return normalized, questions


def demote_deferred_blockers(
    blockers: list[Blocker],
    later_task_ids: list[str],
) -> list[Blocker]:
    """Demote a blocker that only defers work to a later unit of the plan.

    The plan already schedules that work, so it cannot need a human: the
    message is kept, as information, and the batch moves on to that unit.
    """

    ids = [task_id for task_id in later_task_ids if task_id]

    if not ids:
        return blockers

    return [
        replace(
            blocker,
            kind=BlockerKind.INFORMATION,
            blocking=False,
            requires_human_input=False,
        )
        if blocker.blocking and any(task_id in blocker.message for task_id in ids)
        else blocker
        for blocker in blockers
    ]


def coerce_blocker(
    value: Any,
) -> Blocker | None:
    """Build a blocker from state or from a provider payload.

    A bare string is legacy persisted data. It keeps the behaviour it had
    when it was written: an opaque, blocking impediment.
    """

    if isinstance(value, Blocker):
        return value

    if isinstance(value, str):
        if not value.strip():
            return None

        return Blocker(
            message=value,
            kind=BlockerKind.EXTERNAL_DEPENDENCY,
            scope=BlockerScope.EXTERNAL,
            fixable_by_agent=False,
            requires_human_input=True,
            blocking=True,
        )

    if not isinstance(value, dict):
        return None

    message = value.get("message")

    if not isinstance(message, str) or not message.strip():
        return None

    try:
        kind = BlockerKind(
            str(value.get("kind", "")).strip().upper()
        )
    except ValueError:
        kind = BlockerKind.INFORMATION

    try:
        scope = BlockerScope(
            str(value.get("scope", "")).strip().upper()
        )
    except ValueError:
        scope = BlockerScope.PROJECT

    return Blocker(
        message=message,
        kind=kind,
        scope=scope,
        fixable_by_agent=bool(
            value.get("fixable_by_agent", False)
        ),
        requires_human_input=bool(
            value.get("requires_human_input", False)
        ),
        blocking=bool(
            value.get("blocking", True)
        ),
    )


def coerce_blockers(
    values: Any,
) -> list[Blocker]:
    """Build the blocker list of a result, from any supported shape."""

    if not isinstance(values, (list, tuple)):
        return []

    blockers = [
        coerce_blocker(value)
        for value in values
    ]

    return [
        blocker
        for blocker in blockers
        if blocker is not None
    ]


def serialize_blocker(
    blocker: Blocker,
) -> dict[str, Any]:
    return {
        "message": blocker.message,
        "kind": blocker.kind.value,
        "scope": blocker.scope.value,
        "fixable_by_agent": blocker.fixable_by_agent,
        "requires_human_input": blocker.requires_human_input,
        "blocking": blocker.blocking,
    }


def serialize_blockers(
    blockers: list[Blocker],
) -> list[dict[str, Any]]:
    return [
        serialize_blocker(blocker)
        for blocker in blockers
    ]


def blocker_messages(
    blockers: list[Blocker],
) -> list[str]:
    return [
        blocker.message
        for blocker in blockers
    ]


def validate_declared_blockers(
    values: Any,
) -> None:
    """Validate the *structure* of blockers coming out of a producer.

    Legacy prose is accepted when reading old state, never when producing
    new work: a new response must declare what kind of impediment it means.

    Only representations the Factory cannot interpret are refused - a
    missing message, an unknown kind or scope, a flag that is not a boolean.
    Field *combinations* are never refused here. The published response
    schema constrains each field independently and cannot express a
    cross-field rule, so every combination of those fields is a response the
    Factory told the model it could return. Deciding what such a combination
    is worth is `is_effectively_blocking`, and demoting it is
    `normalize_blockers`; raising instead would let one boolean in an
    untrusted response terminate the workflow.
    """

    if not isinstance(values, (list, tuple)):
        raise ValueError(
            "Blockers must be a list of structured blocker objects."
        )

    for value in values:
        if isinstance(value, Blocker):
            continue

        if not isinstance(value, dict):
            raise ValueError(
                "Each blocker must be a structured blocker object with "
                "message, kind, scope, fixable_by_agent, "
                "requires_human_input and blocking: "
                f"{value!r}"
            )

        message = value.get("message")

        if not isinstance(message, str) or not message.strip():
            raise ValueError(
                "Blocker message is required."
            )

        kind = str(value.get("kind", "")).strip().upper()

        if kind not in BLOCKER_KIND_VALUES:
            raise ValueError(
                "Blocker kind must be one of "
                f"{', '.join(BLOCKER_KIND_VALUES)}: {message}"
            )

        scope = str(value.get("scope", "")).strip().upper()

        if scope not in BLOCKER_SCOPE_VALUES:
            raise ValueError(
                "Blocker scope must be one of "
                f"{', '.join(BLOCKER_SCOPE_VALUES)}: {message}"
            )

        for flag in (
            "fixable_by_agent",
            "requires_human_input",
            "blocking",
        ):
            if flag in value and not isinstance(value[flag], bool):
                raise ValueError(
                    f"Blocker {flag} must be a boolean: {message}"
                )
