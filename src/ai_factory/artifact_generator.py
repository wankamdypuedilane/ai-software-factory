from typing import Any, Protocol

from ai_factory.artifact_prompt import build_artifact_prompt
from ai_factory.artifact_request import ArtifactGenerationTask


class ArtifactProvider(Protocol):
    def generate(self, prompt: str) -> str:
        """Generate raw artifact content from a prompt."""
        ...


def generate_artifact(
    task: ArtifactGenerationTask,
    context: dict[str, Any],
    provider: ArtifactProvider,
) -> str:
    """Generate the content of one requested artifact."""

    prompt = build_artifact_prompt(
        task=task,
        context=context,
    )

    content = provider.generate(prompt)

    if not isinstance(content, str):
        raise TypeError(
            "Artifact provider must return a string."
        )

    content = content.strip()

    if not content:
        raise ValueError(
            f"Artifact generation returned empty content for '{task.path}'."
        )

    return content
