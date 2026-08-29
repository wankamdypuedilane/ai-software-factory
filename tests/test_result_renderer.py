from ai_factory.agent_result import (
    AgentArtifact,
    AgentResult,
)
from ai_factory.result_renderer import render_agent_result


def test_render_agent_result_displays_core_fields() -> None:
    result = AgentResult(
        status="NEEDS_INPUT",
        summary="More product context is required.",
        questions=[
            "What problem should the product solve?",
            "Who are the target users?",
        ],
        blockers=[
            "Missing product vision.",
        ],
        handoff=None,
    )

    output = render_agent_result(
        "product",
        result,
    )

    assert "Agent: product" in output
    assert "Status: NEEDS_INPUT" in output
    assert "Summary:" in output
    assert "More product context is required." in output
    assert "Questions:" in output
    assert "- What problem should the product solve?" in output
    assert "Blockers:" in output
    assert "- Missing product vision." in output
    assert "Handoff: none" in output


def test_render_agent_result_displays_artifacts_and_handoff() -> None:
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
    )

    output = render_agent_result(
        "architect",
        result,
    )

    assert "Artifacts:" in output
    assert "- knowledge/architecture/system.md" in output
    assert "Handoff: developer" in output


def test_render_agent_result_omits_empty_optional_sections() -> None:
    result = AgentResult(
        status="COMPLETED",
        summary="Done.",
    )

    output = render_agent_result(
        "qa",
        result,
    )

    assert "Questions:" not in output
    assert "Blockers:" not in output
    assert "Artifacts:" not in output
    assert "Handoff: none" in output
