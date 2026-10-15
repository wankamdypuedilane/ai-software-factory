"""Structured execution contract for implementation units.

The Factory decides how to execute an implementation unit from these values
alone. Nothing here inspects a title, a purpose, or any other prose.
"""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class ImplementationTaskKind(str, Enum):
    """What an implementation unit produces."""

    IMPLEMENTATION = "IMPLEMENTATION"
    TEST_IMPLEMENTATION = "TEST_IMPLEMENTATION"
    VERIFICATION = "VERIFICATION"


class ImplementationScope(str, Enum):
    """How much of the project an implementation unit covers."""

    TASK = "TASK"
    PROJECT = "PROJECT"


@dataclass(frozen=True)
class VerificationPolicy:
    """How the runtime is allowed to validate an implementation unit."""

    allow_full_suite: bool = False
    baseline_required: bool = True


TASK_KIND_VALUES = tuple(
    kind.value
    for kind in ImplementationTaskKind
)

SCOPE_VALUES = tuple(
    scope.value
    for scope in ImplementationScope
)


def coerce_task_kind(
    value: Any,
) -> ImplementationTaskKind | None:
    """Return a task kind, or None when the unit declares none."""

    if isinstance(value, ImplementationTaskKind):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return ImplementationTaskKind(
            value.strip().upper()
        )
    except ValueError:
        return None


def coerce_scope(
    value: Any,
) -> ImplementationScope | None:
    """Return a scope, or None when the unit declares none."""

    if isinstance(value, ImplementationScope):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return ImplementationScope(
            value.strip().upper()
        )
    except ValueError:
        return None


def coerce_verification_policy(
    value: Any,
) -> VerificationPolicy | None:
    """Return a verification policy, or None when the unit declares none."""

    if isinstance(value, VerificationPolicy):
        return value

    if not isinstance(value, dict):
        return None

    allow_full_suite = value.get("allow_full_suite")
    baseline_required = value.get("baseline_required")

    if not isinstance(allow_full_suite, bool):
        return None

    if not isinstance(baseline_required, bool):
        return None

    return VerificationPolicy(
        allow_full_suite=allow_full_suite,
        baseline_required=baseline_required,
    )


def default_verification_policy(
    kind: ImplementationTaskKind,
    scope: ImplementationScope | None = None,
) -> VerificationPolicy:
    """Return the policy implied by a declared kind and scope.

    Only a verification unit covering the whole project may run the
    full-project suite, and only such a unit skips its baseline: every
    narrower unit must be protected from unrelated pre-existing failures.
    """

    if (
        kind is ImplementationTaskKind.VERIFICATION
        and scope is ImplementationScope.PROJECT
    ):
        return VerificationPolicy(
            allow_full_suite=True,
            baseline_required=False,
        )

    return VerificationPolicy(
        allow_full_suite=False,
        baseline_required=True,
    )


def clamp_verification_policy(
    kind: ImplementationTaskKind | None,
    scope: ImplementationScope | None,
    verification: VerificationPolicy | None,
) -> VerificationPolicy | None:
    """Reduce a declared policy to what its kind and scope permit.

    Only a PROJECT-scoped VERIFICATION unit may run the full test suite. A
    unit claiming otherwise is not refused: the published response schema
    declares these three fields independently and cannot express the rule
    tying them together, so the claim is a response the Factory said was
    allowed. It is reduced instead - strictly downwards, never upwards - so
    the rule holds without one field of an untrusted response being able to
    end the run.
    """

    if verification is None:
        return None

    if not verification.allow_full_suite:
        return verification

    if kind is None or scope is None:
        return replace(
            verification,
            allow_full_suite=False,
        )

    if default_verification_policy(kind, scope).allow_full_suite:
        return verification

    return replace(
        verification,
        allow_full_suite=False,
    )


def validate_declared_contract(
    request: Any,
) -> None:
    """Validate the contract of a freshly produced implementation request.

    This guards the producer boundary only. A unit coming out of an agent
    must declare its contract, so a new task can never fall silently into
    the legacy heuristic. Reading a task persisted before the contract
    existed does not go through here.
    """

    task_id = getattr(request, "id", "")

    if request.kind is None:
        raise ValueError(
            "Implementation request must declare kind "
            f"({', '.join(TASK_KIND_VALUES)}): {task_id}"
        )

    if request.scope is None:
        raise ValueError(
            "Implementation request must declare scope "
            f"({', '.join(SCOPE_VALUES)}): {task_id}"
        )

    if request.verification is None:
        raise ValueError(
            "Implementation request must declare verification "
            "with allow_full_suite and baseline_required: "
            f"{task_id}"
        )

    # An over-claimed full suite is not refused here. `clamp_verification_
    # policy` reduces it at the producer boundary, and the runtime refuses
    # the offending command anyway, so the rule is enforced twice without a
    # fatal path.


def validate_declared_contracts(
    requests: list[Any],
) -> None:
    """Validate every implementation request produced by an agent."""

    for request in requests:
        validate_declared_contract(request)


def serialize_verification_policy(
    policy: VerificationPolicy,
) -> dict[str, bool]:
    return {
        "allow_full_suite": policy.allow_full_suite,
        "baseline_required": policy.baseline_required,
    }


def serialize_contract_fields(
    kind: ImplementationTaskKind | None,
    scope: ImplementationScope | None,
    verification: VerificationPolicy | None,
) -> dict[str, Any]:
    """Serialize only the contract fields a unit actually declares.

    An undeclared contract serializes to nothing, so a legacy unit keeps its
    previous persisted shape.
    """

    serialized: dict[str, Any] = {}

    if kind is not None:
        serialized["kind"] = kind.value

    if scope is not None:
        serialized["scope"] = scope.value

    if verification is not None:
        serialized["verification"] = (
            serialize_verification_policy(
                verification
            )
        )

    return serialized
