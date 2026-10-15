"""Every implementation unit must produce evidence that it worked.

The outcome model was satisfied by empty collections: `all([])` is True and
`len([]) >= len([])` is True, so a unit declaring no verification command at
all passed setup, passed "tests executed" and passed validation without a
single command running. The model could opt out of being verified simply by
returning an empty list.

The requirement is derived from the declared task contract rather than from a
title or a summary. Across every supported kind and scope the answer is the
same, and the audit that produced this module says why:

    kind                 scope    may write files  may run commands  zero OK
    IMPLEMENTATION       TASK     yes              yes               no
    IMPLEMENTATION       PROJECT  yes              yes               no
    TEST_IMPLEMENTATION  TASK     yes (tests)      yes               no
    TEST_IMPLEMENTATION  PROJECT  yes (tests)      yes               no
    VERIFICATION         TASK     rarely           yes               no
    VERIFICATION         PROJECT  rarely           yes (full suite)  no

A unit that writes governed files has something to prove. A unit that writes
nothing exists only to run validations, so it has nothing else to offer. The
contract has no metadata-only kind, and inventing one to escape this rule is
exactly what the rule exists to prevent. What the contract does decide is
*which* commands are acceptable - full suite or task-scoped - and that is
`VerificationPolicy`, unchanged here.
"""

from dataclasses import dataclass

from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
)
from ai_factory.implementation_result import ImplementationResult


@dataclass(frozen=True)
class ValidationRequirement:
    """Whether a unit of this contract must declare a validation."""

    required: bool
    reason: str


def describe_validation_requirement(
    kind: ImplementationTaskKind | None = None,
    scope: ImplementationScope | None = None,
) -> ValidationRequirement:
    """Return the validation requirement implied by a declared contract.

    No supported kind may execute without evidence, so this is uniform. It
    stays an explicit function rather than a constant because the contract is
    the authority: a future kind that genuinely needs different semantics is
    added here, deliberately, and not by an empty list slipping through.
    """

    return ValidationRequirement(
        required=True,
        reason=(
            "Every implementation unit must declare at least one validation "
            "command the Factory can execute."
        ),
    )


def changes_governed_state(
    result: ImplementationResult,
) -> bool:
    """Whether this unit would write files the Factory governs."""

    return bool(result.files)


def missing_validation_evidence(
    result: ImplementationResult,
    kind: ImplementationTaskKind | None = None,
    scope: ImplementationScope | None = None,
) -> str:
    """Return why this unit cannot be validated, or an empty string.

    Only the declared command list is consulted. A summary claiming the tests
    pass is a proposal, not evidence.
    """

    if result.tests:
        return ""

    if not describe_validation_requirement(kind, scope).required:
        return ""

    if changes_governed_state(result):
        return (
            "This response changes "
            f"{len(result.files)} governed file(s) and declares no "
            "validation command, so nothing would verify the change."
        )

    return (
        "This response declares no file change and no validation command, "
        "so it produces no evidence of anything."
    )


def build_missing_validation_correction(
    task_id: str,
    result: ImplementationResult,
    reason: str,
) -> list[str]:
    """Ask the agent for the validation its response is missing."""

    corrections = [
        "The previous response was rejected by the Factory runtime and "
        "was not applied.",
        f"Return a corrected response for task {task_id}.",
        f"Reason: {reason}",
        "Return at least one validation command in tests.",
        "For targeted Node.js tests, use: npm test -- <test-file>.",
    ]

    test_files = [
        file_change.path
        for file_change in result.files
        if file_change.path.replace("\\", "/").split("/")[-1].count(".test.")
    ]

    if test_files:
        corrections.extend(
            [
                "Test files produced by this task: "
                + ", ".join(dict.fromkeys(test_files))
                + ".",
                "Scope the validation command to those test files.",
            ]
        )
    else:
        corrections.append(
            "This task returned no test file, so add the automated test it "
            "requires and scope the validation command to that test file."
        )

    corrections.extend(
        [
            "A summary stating that tests pass is not evidence; only a "
            "command the Factory executes is.",
            "Keep the rest of the implementation unchanged.",
            "Do not report this correction as a blocker.",
        ]
    )

    return corrections
