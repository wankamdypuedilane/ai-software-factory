from pathlib import Path

from ai_factory.agent_result import AgentArtifactRequest
from ai_factory.artifact_pipeline import generate_requested_artifacts


class FakeArtifactProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        if "vision.md" in prompt:
            return "# Product Vision\n\nVision content."

        if "requirements.md" in prompt:
            return "# Requirements\n\nRequirements content."

        return "# Artifact\n\nGenerated content."


def test_generate_requested_artifacts_generates_and_writes_files(
    tmp_path: Path,
) -> None:
    requests = [
        AgentArtifactRequest(
            path="knowledge/project/vision.md",
            purpose="Document the product vision.",
        ),
        AgentArtifactRequest(
            path="knowledge/project/requirements.md",
            purpose="Document the MVP requirements.",
        ),
    ]

    context = {
        "project": {
            "project": {
                "name": "Test Project",
            }
        },
        "state": {},
        "human_input": "Build a ride-hailing application.",
    }

    provider = FakeArtifactProvider()

    generated = generate_requested_artifacts(
        project_root=tmp_path,
        agent_name="product",
        requests=requests,
        context=context,
        provider=provider,
    )

    assert len(generated) == 2
    assert len(provider.prompts) == 2

    vision_path = (
        tmp_path
        / "knowledge"
        / "project"
        / "vision.md"
    )

    requirements_path = (
        tmp_path
        / "knowledge"
        / "project"
        / "requirements.md"
    )

    assert vision_path.exists()
    assert requirements_path.exists()

    assert (
        vision_path.read_text(encoding="utf-8")
        == "# Product Vision\n\nVision content."
    )

    assert (
        requirements_path.read_text(encoding="utf-8")
        == "# Requirements\n\nRequirements content."
    )

    assert generated[0].path == "knowledge/project/vision.md"
    assert generated[0].absolute_path == vision_path

    assert generated[1].path == (
        "knowledge/project/requirements.md"
    )
    assert generated[1].absolute_path == requirements_path


def test_generate_requested_artifacts_returns_empty_list_without_requests(
    tmp_path: Path,
) -> None:
    provider = FakeArtifactProvider()

    generated = generate_requested_artifacts(
        project_root=tmp_path,
        agent_name="product",
        requests=[],
        context={},
        provider=provider,
    )

    assert generated == []
    assert provider.prompts == []
