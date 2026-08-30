from ai_factory.agent_result import (
    AgentArtifactRequest,
    AgentResult,
)
from ai_factory.design_gate_runtime import (
    update_design_gate_from_result,
)


def test_update_design_gate_marks_ready_when_all_deliverables_exist() -> None:
    state = {
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="UX/UI completed.",
        artifact_requests=[
            AgentArtifactRequest(
                path="design/ux-ui/user-flows.md",
                purpose="Document user flows.",
            ),
            AgentArtifactRequest(
                path="design/ux-ui/screen-specs.md",
                purpose="Document screen specifications.",
            ),
        ],
        blockers=[],
    )

    updated_state = update_design_gate_from_result(
        state=state,
        result=result,
        generated_paths=[
            "design/ux-ui/user-flows.md",
            "design/ux-ui/screen-specs.md",
        ],
    )

    gate = updated_state["design_gate"]

    assert gate["status"] == "READY_FOR_REVIEW"
    assert gate["groups"]["deliverables"] == {
        "approved": 2,
        "total": 2,
    }
    assert gate["external_blockers"] == []
    assert gate["human_approval"] is False


def test_update_design_gate_marks_partial_when_deliverables_are_missing() -> None:
    state = {
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="UX/UI partially completed.",
        artifact_requests=[
            AgentArtifactRequest(
                path="design/ux-ui/user-flows.md",
                purpose="Document user flows.",
            ),
            AgentArtifactRequest(
                path="design/ux-ui/screen-specs.md",
                purpose="Document screen specifications.",
            ),
        ],
    )

    updated_state = update_design_gate_from_result(
        state=state,
        result=result,
        generated_paths=[
            "design/ux-ui/user-flows.md",
        ],
    )

    gate = updated_state["design_gate"]

    assert gate["status"] == "PARTIAL"
    assert gate["groups"]["deliverables"] == {
        "approved": 1,
        "total": 2,
    }


def test_update_design_gate_marks_partial_when_blockers_exist() -> None:
    state = {
        "design_gate": {
            "status": "NOT_STARTED",
            "groups": {},
            "external_blockers": [],
            "human_approval": False,
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="UX/UI completed with blocker.",
        artifact_requests=[
            AgentArtifactRequest(
                path="design/ux-ui/user-flows.md",
                purpose="Document user flows.",
            )
        ],
        blockers=[
            "External design review required.",
        ],
    )

    updated_state = update_design_gate_from_result(
        state=state,
        result=result,
        generated_paths=[
            "design/ux-ui/user-flows.md",
        ],
    )

    gate = updated_state["design_gate"]

    assert gate["status"] == "PARTIAL"
    assert gate["external_blockers"] == [
        "External design review required."
    ]
