import pytest

from ai_factory.agent_result import (
    AgentArtifact,
    AgentResult,
)
from ai_factory.result_application import apply_agent_result


def test_apply_agent_result_updates_agent_status_and_last_result() -> None:
    state = {
        "agents": {
            "product": {
                "status": "READY",
            }
        }
    }

    result = AgentResult(
        status="NEEDS_INPUT",
        summary="More product context is required.",
        questions=[
            "What problem should the product solve?",
        ],
        blockers=[
            "Missing product vision.",
        ],
        handoff=None,
    )

    updated_state = apply_agent_result(
        state,
        "product",
        result,
    )

    product = updated_state["agents"]["product"]

    assert product["status"] == "BLOCKED"
    assert product["last_result"]["status"] == "NEEDS_INPUT"
    assert (
        product["last_result"]["summary"]
        == "More product context is required."
    )
    assert product["last_result"]["questions"] == [
        "What problem should the product solve?"
    ]
    assert product["last_result"]["blockers"] == [
        "Missing product vision."
    ]
    assert product["last_result"]["handoff"] is None
    assert product["last_result"]["artifacts"] == []
    assert product["last_result"]["metadata"] == {}


def test_apply_agent_result_records_artifact_paths() -> None:
    state = {
        "agents": {
            "architect": {
                "status": "IN_PROGRESS",
            }
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Architecture completed.",
        artifacts=[
            AgentArtifact(
                path="knowledge/architecture/system.md",
                content="# Architecture",
            )
        ],
        handoff="developer",
        metadata={
            "confidence": "high",
        },
    )

    updated_state = apply_agent_result(
        state,
        "architect",
        result,
    )

    architect = updated_state["agents"]["architect"]

    assert architect["status"] == "REVIEW_REQUIRED"
    assert architect["last_result"]["artifacts"] == [
        "knowledge/architecture/system.md"
    ]
    assert architect["last_result"]["handoff"] == "developer"
    assert architect["last_result"]["metadata"] == {
        "confidence": "high"
    }


def test_apply_agent_result_rejects_unknown_agent() -> None:
    state = {
        "agents": {}
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Done.",
    )

    with pytest.raises(
        KeyError,
        match="Unknown agent",
    ):
        apply_agent_result(
            state,
            "unknown",
            result,
        )
