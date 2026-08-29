import pytest

from ai_factory.artifact_generator import generate_artifact
from ai_factory.artifact_request import ArtifactGenerationTask


class FakeArtifactProvider:
    def __init__(self) -> None:
        self.received_prompt: str | None = None

    def generate(self, prompt: str) -> str:
        self.received_prompt = prompt
        return "# Product Vision\n\nGenerated content."


def test_generate_artifact_builds_prompt_and_returns_content() -> None:
    task = ArtifactGenerationTask(
        agent_name="product",
        path="knowledge/project/vision.md",
        purpose="Document the product vision.",
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

    provider = FakeArtifactProvider()

    content = generate_artifact(
        task=task,
        context=context,
        provider=provider,
    )

    assert content == "# Product Vision\n\nGenerated content."

    assert provider.received_prompt is not None
    assert "Agent: product" in provider.received_prompt
    assert "knowledge/project/vision.md" in provider.received_prompt
    assert "Document the product vision." in provider.received_prompt


def test_generate_artifact_rejects_empty_content() -> None:
    class EmptyProvider:
        def generate(self, prompt: str) -> str:
            return "   "

    task = ArtifactGenerationTask(
        agent_name="product",
        path="knowledge/project/vision.md",
        purpose="Document the product vision.",
    )

    with pytest.raises(
        ValueError,
        match="returned empty content",
    ):
        generate_artifact(
            task=task,
            context={},
            provider=EmptyProvider(),
        )


def test_generate_artifact_rejects_non_string_content() -> None:
    class InvalidProvider:
        def generate(self, prompt: str):
            return None

    task = ArtifactGenerationTask(
        agent_name="product",
        path="knowledge/project/vision.md",
        purpose="Document the product vision.",
    )

    with pytest.raises(
        TypeError,
        match="must return a string",
    ):
        generate_artifact(
            task=task,
            context={},
            provider=InvalidProvider(),
        )
