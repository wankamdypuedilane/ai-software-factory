from ai_factory.agent_result import (
    AgentArtifact,
    AgentResult,
)


def test_agent_result_has_safe_default_collections() -> None:
    result = AgentResult(
        status="NEEDS_INPUT",
        summary="More information is required.",
    )

    assert result.status == "NEEDS_INPUT"
    assert result.summary == "More information is required."
    assert result.artifacts == []
    assert result.questions == []
    assert result.blockers == []
    assert result.handoff is None
    assert result.metadata == {}


def test_agent_result_stores_artifacts_and_handoff() -> None:
    artifact = AgentArtifact(
        path="knowledge/product/requirements.md",
        content="# Requirements",
    )

    result = AgentResult(
        status="COMPLETED",
        summary="Product discovery completed.",
        artifacts=[artifact],
        handoff="ux_ui",
    )

    assert len(result.artifacts) == 1
    assert result.artifacts[0].path == (
        "knowledge/product/requirements.md"
    )
    assert result.artifacts[0].content == "# Requirements"
    assert result.handoff == "ux_ui"


def test_agent_result_default_collections_are_independent() -> None:
    first = AgentResult(
        status="COMPLETED",
        summary="First",
    )

    second = AgentResult(
        status="COMPLETED",
        summary="Second",
    )

    first.questions.append("A question")

    assert first.questions == ["A question"]
    assert second.questions == []
