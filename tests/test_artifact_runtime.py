from pathlib import Path

from ai_factory.agent_result import (
    AgentArtifactRequest,
    AgentResult,
)
from ai_factory.artifact_runtime import run_artifact_generation


class FakeArtifactProvider:
    def generate(self, prompt: str) -> str:
        if "vision.md" in prompt:
            return "# Product Vision\n\nGenerated vision."

        return "# Generated Artifact"


def test_run_artifact_generation_generates_requested_files(
    tmp_path: Path,
) -> None:
    result = AgentResult(
        status="COMPLETED",
        summary="Product discovery completed.",
        artifact_requests=[
            AgentArtifactRequest(
                path="knowledge/project/vision.md",
                purpose="Document the product vision.",
            )
        ],
        handoff="ux_ui",
    )

    context = {
        "project": {
            "project": {
                "name": "Test Project",
            }
        },
        "state": {},
        "human_input": "Build a ride-hailing application.",
    }

    generated = run_artifact_generation(
        project_root=tmp_path,
        agent_name="product",
        result=result,
        context=context,
        provider=FakeArtifactProvider(),
    )

    assert len(generated) == 1
    assert generated[0].path == "knowledge/project/vision.md"

    target = (
        tmp_path
        / "knowledge"
        / "project"
        / "vision.md"
    )

    assert target.exists()
    assert target.read_text(
        encoding="utf-8",
    ) == "# Product Vision\n\nGenerated vision."


def test_run_artifact_generation_skips_when_no_requests(
    tmp_path: Path,
) -> None:
    result = AgentResult(
        status="COMPLETED",
        summary="Done.",
    )

    generated = run_artifact_generation(
        project_root=tmp_path,
        agent_name="product",
        result=result,
        context={},
        provider=FakeArtifactProvider(),
    )

    assert generated == []
