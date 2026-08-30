import pytest

from ai_factory.agent_result import (
    AgentArtifact,
    AgentArtifactRequest,
    AgentImplementationRequest,
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


def test_apply_agent_result_records_artifact_requests() -> None:
    state = {
        "agents": {
            "product": {
                "status": "READY",
            }
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Product discovery completed.",
        artifact_requests=[
            AgentArtifactRequest(
                path="knowledge/product/requirements.md",
                purpose="Document the approved MVP requirements.",
            )
        ],
        handoff="ux_ui",
    )

    updated_state = apply_agent_result(
        state,
        "product",
        result,
    )

    requests = updated_state[
        "agents"
    ]["product"]["last_result"]["artifact_requests"]

    assert requests == [
        {
            "path": "knowledge/product/requirements.md",
            "purpose": "Document the approved MVP requirements.",
        }
    ]


def test_apply_agent_result_records_implementation_requests() -> None:
    state = {
        "agents": {
            "developer": {
                "status": "READY",
            }
        }
    }

    result = AgentResult(
        status="COMPLETED",
        summary="Implementation planning completed.",
        implementation_requests=[
            AgentImplementationRequest(
                id="US-001",
                title="Passenger authentication",
                purpose="Implement authentication with automated tests.",
            ),
            AgentImplementationRequest(
                id="US-002",
                title="Ride request workflow",
                purpose="Implement ride creation and status handling.",
            ),
        ],
        handoff="qa",
    )

    updated_state = apply_agent_result(
        state,
        "developer",
        result,
    )

    requests = updated_state[
        "agents"
    ]["developer"]["last_result"]["implementation_requests"]

    assert requests == [
        {
            "id": "US-001",
            "title": "Passenger authentication",
            "purpose": "Implement authentication with automated tests.",
        },
        {
            "id": "US-002",
            "title": "Ride request workflow",
            "purpose": "Implement ride creation and status handling.",
        },
    ]
