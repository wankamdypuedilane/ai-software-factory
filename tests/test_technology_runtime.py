import pytest

from ai_factory.agent_result import AgentResult
from ai_factory.technology_runtime import (
    build_technology_proposal_from_architect_result,
    update_technology_gate_from_architect_result,
)


def test_build_technology_proposal_from_architect_result() -> None:
    proposal = {
        "components": [
            {
                "name": "frontend",
                "technology": "React",
                "rationale": "Suitable for the web UI.",
            },
            {
                "name": "backend",
                "technology": "Django",
                "rationale": "Suitable for the monolithic backend.",
            },
        ]
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Architecture completed.",
        metadata={
            "technology_proposal": proposal,
        },
    )

    assert build_technology_proposal_from_architect_result(
        result
    ) == {
        "components": {
            "frontend": {
                "technology": "React",
                "rationale": "Suitable for the web UI.",
            },
            "backend": {
                "technology": "Django",
                "rationale": "Suitable for the monolithic backend.",
            },
        }
    }


def test_build_technology_proposal_rejects_missing_proposal() -> None:
    result = AgentResult(
        status="COMPLETED",
        summary="Architecture completed.",
    )

    with pytest.raises(
        ValueError,
        match="does not contain a technology proposal",
    ):
        build_technology_proposal_from_architect_result(
            result,
        )


def test_update_technology_gate_submits_architect_proposal() -> None:
    state = {
        "technology_gate": {
            "status": "NOT_STARTED",
            "human_approval": False,
            "proposal": {},
        }
    }

    config = {
        "technology": {
            "selection_mode": "recommend",
            "constraints": {},
            "selected": {},
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Architecture completed.",
        metadata={
            "technology_proposal": {
                "components": [
                    {
                        "name": "frontend",
                        "technology": "React",
                        "rationale": "Suitable for the web UI.",
                    },
                ]
            }
        },
    )

    updated_state = update_technology_gate_from_architect_result(
        state=state,
        config=config,
        result=result,
    )

    gate = updated_state["technology_gate"]

    assert gate["status"] == "REVIEW_REQUIRED"
    assert gate["human_approval"] is False
    assert gate["proposal"] == {
        "components": {
            "frontend": {
                "technology": "React",
                "rationale": "Suitable for the web UI.",
            }
        }
    }


def test_update_technology_gate_skips_when_gate_not_required() -> None:
    state = {
        "technology_gate": {
            "status": "NOT_STARTED",
            "human_approval": False,
            "proposal": {},
        }
    }

    config = {
        "technology": {
            "selection_mode": "manual",
            "constraints": {},
            "selected": {},
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Architecture completed.",
    )

    updated_state = update_technology_gate_from_architect_result(
        state=state,
        config=config,
        result=result,
    )

    assert updated_state == state
