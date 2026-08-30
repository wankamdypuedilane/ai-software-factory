import pytest

from ai_factory.design_gate_runtime import (
    rebuild_design_gate_from_state,
)


def test_rebuild_design_gate_from_persisted_ux_ui_result() -> None:
    state = {
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "artifact_requests": [
                        {
                            "path": "design/ux-ui/user-flows.md",
                            "purpose": "Document user flows.",
                        },
                        {
                            "path": "design/ux-ui/screen-specs.md",
                            "purpose": "Document screen specifications.",
                        },
                    ],
                    "generated_artifacts": [
                        "design/ux-ui/user-flows.md",
                        "design/ux-ui/screen-specs.md",
                    ],
                    "blockers": [],
                },
            }
        },
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        },
    }

    updated_state = rebuild_design_gate_from_state(
        state,
    )

    gate = updated_state["design_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["groups"]["deliverables"] == {
        "approved": 2,
        "total": 2,
    }
    assert gate["external_blockers"] == []
    assert gate["human_approval"] is False


def test_rebuild_design_gate_marks_partial_when_artifacts_missing() -> None:
    state = {
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
                "last_result": {
                    "artifact_requests": [
                        {
                            "path": "design/ux-ui/user-flows.md",
                            "purpose": "Document user flows.",
                        },
                        {
                            "path": "design/ux-ui/screen-specs.md",
                            "purpose": "Document screen specifications.",
                        },
                    ],
                    "generated_artifacts": [
                        "design/ux-ui/user-flows.md",
                    ],
                    "blockers": [],
                },
            }
        },
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        },
    }

    updated_state = rebuild_design_gate_from_state(
        state,
    )

    gate = updated_state["design_gate"]

    assert gate["status"] == "PARTIAL"
    assert gate["groups"]["deliverables"] == {
        "approved": 1,
        "total": 2,
    }


def test_rebuild_design_gate_rejects_missing_ux_ui_result() -> None:
    state = {
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
            }
        },
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="persisted result",
    ):
        rebuild_design_gate_from_state(
            state,
        )


def test_rebuild_design_gate_restores_existing_human_approval() -> None:
    state = {
        "approvals": {
            "design": True,
        },
        "agents": {
            "ux_ui": {
                "status": "APPROVED",
                "last_result": {
                    "artifact_requests": [
                        {
                            "path": "design/ux-ui/user-flows.md",
                            "purpose": "Document user flows.",
                        },
                        {
                            "path": "design/ux-ui/screen-specs.md",
                            "purpose": "Document screen specifications.",
                        },
                    ],
                    "generated_artifacts": [
                        "design/ux-ui/user-flows.md",
                        "design/ux-ui/screen-specs.md",
                    ],
                    "blockers": [],
                },
            }
        },
        "design_gate": {
            "status": "READY_FOR_REVIEW",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        },
    }

    updated_state = rebuild_design_gate_from_state(
        state,
    )

    gate = updated_state["design_gate"]

    assert gate["status"] == "APPROVED"
    assert gate["human_approval"] is True
    assert gate["groups"]["deliverables"] == {
        "approved": 2,
        "total": 2,
    }
    assert gate["external_blockers"] == []
