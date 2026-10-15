"""A model must not be able to block a gate by asserting that it is blocked.

LinkVault round 2 deadlocked because UX/UI returned "Human approval is
required for the visual identity" as a blocker, which became an external
blocker on the very Design Gate that human approval would have cleared.
Only a declared, unfixable external dependency may block anything.
"""

import pytest

from ai_factory.agent_result import (
    AgentArtifactRequest,
    AgentResult,
)
from ai_factory.blocker_contract import (
    Blocker,
    BlockerKind,
    BlockerScope,
    blocking_blockers,
    coerce_blockers,
    is_effectively_blocking,
    normalize_blockers,
    serialize_blockers,
    validate_declared_blockers,
)
from ai_factory.design_gate import is_design_gate_ready
from ai_factory.design_gate_runtime import (
    rebuild_design_gate_from_state,
    update_design_gate_from_result,
)


def _human_decision(
    message: str = "Human approval is required for the visual identity.",
) -> Blocker:
    return Blocker(
        message=message,
        kind=BlockerKind.HUMAN_DECISION,
        scope=BlockerScope.PROJECT,
        fixable_by_agent=False,
        requires_human_input=True,
        blocking=True,
    )


def _external_dependency(
    message: str = "The payment provider sandbox credentials are unavailable.",
) -> Blocker:
    return Blocker(
        message=message,
        kind=BlockerKind.EXTERNAL_DEPENDENCY,
        scope=BlockerScope.EXTERNAL,
        fixable_by_agent=False,
        requires_human_input=True,
        blocking=True,
    )


def _local_defect(
    message: str = "The generated route file must be corrected.",
) -> Blocker:
    return Blocker(
        message=message,
        kind=BlockerKind.LOCAL_DEFECT,
        scope=BlockerScope.WORKSPACE,
        fixable_by_agent=True,
        requires_human_input=False,
        blocking=True,
    )


# --------------------------------------------------------------------------
# Authority: only an external dependency can block
# --------------------------------------------------------------------------


def test_only_an_external_dependency_can_block() -> None:
    assert is_effectively_blocking(_external_dependency()) is True
    assert is_effectively_blocking(_human_decision()) is False
    assert is_effectively_blocking(_local_defect()) is False
    assert is_effectively_blocking(
        Blocker(
            message="Note.",
            kind=BlockerKind.INFORMATION,
            scope=BlockerScope.PROJECT,
        )
    ) is False


def test_a_fixable_external_dependency_is_not_blocking() -> None:
    """An agent cannot claim an external blocker it could fix itself."""

    assert is_effectively_blocking(
        Blocker(
            message="Dependency missing.",
            kind=BlockerKind.EXTERNAL_DEPENDENCY,
            scope=BlockerScope.EXTERNAL,
            fixable_by_agent=True,
            blocking=True,
        )
    ) is False


def test_normalization_demotes_and_harvests_questions() -> None:
    normalized, questions = normalize_blockers(
        [
            _human_decision(),
            _external_dependency(),
            _local_defect(),
        ]
    )

    assert [b.blocking for b in normalized] == [False, True, False]

    assert questions == [
        "Human approval is required for the visual identity.",
    ]

    assert [b.message for b in blocking_blockers(normalized)] == [
        "The payment provider sandbox credentials are unavailable.",
    ]


# --------------------------------------------------------------------------
# Producer boundary
# --------------------------------------------------------------------------


def test_a_prose_blocker_from_a_producer_is_refused() -> None:
    with pytest.raises(
        ValueError,
        match="structured blocker",
    ):
        validate_declared_blockers(
            [
                "Human approval is required.",
            ]
        )


def test_an_unknown_blocker_kind_is_refused() -> None:
    with pytest.raises(
        ValueError,
        match="kind",
    ):
        validate_declared_blockers(
            [
                {
                    "message": "Something.",
                    "kind": "MADE_UP",
                    "scope": "PROJECT",
                    "fixable_by_agent": False,
                    "requires_human_input": False,
                    "blocking": True,
                }
            ]
        )


def test_a_structured_blocker_from_a_producer_is_accepted() -> None:
    validate_declared_blockers(
        [
            {
                "message": "Sandbox credentials unavailable.",
                "kind": "EXTERNAL_DEPENDENCY",
                "scope": "EXTERNAL",
                "fixable_by_agent": False,
                "requires_human_input": True,
                "blocking": True,
            }
        ]
    )


# --------------------------------------------------------------------------
# Legacy state stays readable
# --------------------------------------------------------------------------


def test_legacy_string_blockers_from_state_stay_readable() -> None:
    blockers = coerce_blockers(
        [
            "Deployment credentials unavailable.",
        ]
    )

    assert blockers[0].message == "Deployment credentials unavailable."
    assert blockers[0].kind is BlockerKind.EXTERNAL_DEPENDENCY
    assert is_effectively_blocking(blockers[0]) is True


def test_structured_blockers_round_trip_through_state() -> None:
    original = [
        _external_dependency(),
        _human_decision(),
    ]

    restored = coerce_blockers(
        serialize_blockers(original)
    )

    assert restored == original


# --------------------------------------------------------------------------
# The LinkVault deadlock, simulated
# --------------------------------------------------------------------------


def _design_state() -> dict:
    return {
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
                "last_result": {},
            }
        },
        "approvals": {"design": False},
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        },
    }


def _ux_result(blockers: list[Blocker]) -> AgentResult:
    return AgentResult(
        status="REVIEW_REQUIRED",
        summary="UX/UI deliverables scoped.",
        artifact_requests=[
            AgentArtifactRequest(
                path=f"knowledge/design/doc{index}.md",
                purpose="Design document.",
            )
            for index in range(3)
        ],
        blockers=blockers,
    )


def test_human_approval_request_leaves_the_design_gate_approvable() -> None:
    """The exact LinkVault round-2 deadlock."""

    state = _design_state()

    update_design_gate_from_result(
        state,
        _ux_result([_human_decision()]),
        generated_paths=[
            "knowledge/design/doc0.md",
            "knowledge/design/doc1.md",
            "knowledge/design/doc2.md",
        ],
    )

    gate = state["design_gate"]

    assert gate["external_blockers"] == []
    assert gate["status"] == "READY_FOR_REVIEW"
    assert is_design_gate_ready(state) is True


def test_a_ux_question_never_becomes_an_external_blocker() -> None:
    state = _design_state()

    result = _ux_result([])
    result.questions = ["Which brand colours should be used?"]

    update_design_gate_from_result(
        state,
        result,
        generated_paths=[
            "knowledge/design/doc0.md",
            "knowledge/design/doc1.md",
            "knowledge/design/doc2.md",
        ],
    )

    assert state["design_gate"]["external_blockers"] == []
    assert is_design_gate_ready(state) is True


def test_a_real_external_dependency_still_blocks_the_gate() -> None:
    state = _design_state()

    update_design_gate_from_result(
        state,
        _ux_result([_external_dependency()]),
        generated_paths=[
            "knowledge/design/doc0.md",
            "knowledge/design/doc1.md",
            "knowledge/design/doc2.md",
        ],
    )

    gate = state["design_gate"]

    assert gate["external_blockers"] == [
        "The payment provider sandbox credentials are unavailable.",
    ]
    assert gate["status"] == "PARTIAL"
    assert is_design_gate_ready(state) is False


def test_a_local_defect_never_blocks_the_gate() -> None:
    state = _design_state()

    update_design_gate_from_result(
        state,
        _ux_result([_local_defect()]),
        generated_paths=[
            "knowledge/design/doc0.md",
            "knowledge/design/doc1.md",
            "knowledge/design/doc2.md",
        ],
    )

    assert state["design_gate"]["external_blockers"] == []
    assert is_design_gate_ready(state) is True


# --------------------------------------------------------------------------
# Public recovery path
# --------------------------------------------------------------------------


def test_a_legitimate_blocker_can_be_resolved_and_the_gate_progresses() -> None:
    from ai_factory.blocker_recovery import resolve_gate_blockers

    state = _design_state()

    update_design_gate_from_result(
        state,
        _ux_result([_external_dependency()]),
        generated_paths=[
            "knowledge/design/doc0.md",
            "knowledge/design/doc1.md",
            "knowledge/design/doc2.md",
        ],
    )

    assert is_design_gate_ready(state) is False

    resolve_gate_blockers(
        state,
        "design",
    )

    assert state["design_gate"]["external_blockers"] == []
    assert is_design_gate_ready(state) is True


def test_a_resolved_blocker_does_not_return_after_a_rebuild() -> None:
    from ai_factory.blocker_recovery import resolve_gate_blockers

    state = _design_state()

    result = _ux_result([_external_dependency()])
    generated = [
        "knowledge/design/doc0.md",
        "knowledge/design/doc1.md",
        "knowledge/design/doc2.md",
    ]

    update_design_gate_from_result(state, result, generated)

    state["agents"]["ux_ui"]["last_result"] = {
        "artifact_requests": [
            {"path": path, "purpose": "Design document."}
            for path in generated
        ],
        "generated_artifacts": generated,
        "blockers": serialize_blockers(result.blockers),
    }

    resolve_gate_blockers(state, "design")

    rebuild_design_gate_from_state(state)

    assert state["design_gate"]["external_blockers"] == []
    assert is_design_gate_ready(state) is True
