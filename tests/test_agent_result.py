from ai_factory.agent_result import (
    AgentArtifact,
    AgentArtifactRequest,
    AgentImplementationRequest,
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


def test_agent_result_stores_artifact_requests() -> None:
    request = AgentArtifactRequest(
        path="knowledge/product/requirements.md",
        purpose="Document the approved MVP requirements.",
    )

    result = AgentResult(
        status="COMPLETED",
        summary="Product discovery completed.",
        artifact_requests=[
            request,
        ],
        handoff="ux_ui",
    )

    assert len(result.artifact_requests) == 1
    assert (
        result.artifact_requests[0].path
        == "knowledge/product/requirements.md"
    )
    assert (
        result.artifact_requests[0].purpose
        == "Document the approved MVP requirements."
    )


def test_agent_result_artifact_request_defaults_are_independent() -> None:
    first = AgentResult(
        status="COMPLETED",
        summary="First",
    )

    second = AgentResult(
        status="COMPLETED",
        summary="Second",
    )

    first.artifact_requests.append(
        AgentArtifactRequest(
            path="knowledge/test.md",
            purpose="Test artifact.",
        )
    )

    assert len(first.artifact_requests) == 1
    assert second.artifact_requests == []


def test_agent_result_supports_implementation_requests() -> None:
    request = AgentImplementationRequest(
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication with automated tests.",
    )

    result = AgentResult(
        status="COMPLETED",
        summary="Implementation planning completed.",
        implementation_requests=[
            request,
        ],
    )

    assert len(result.implementation_requests) == 1

    implementation_request = result.implementation_requests[0]

    assert implementation_request.id == "US-001"
    assert implementation_request.title == "Passenger authentication"
    assert (
        implementation_request.purpose
        == "Implement authentication with automated tests."
    )


def test_agent_result_implementation_requests_default_to_empty() -> None:
    result = AgentResult(
        status="COMPLETED",
        summary="No implementation work requested.",
    )

    assert result.implementation_requests == []
