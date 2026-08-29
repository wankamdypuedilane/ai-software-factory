from pathlib import Path
from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.artifact_generator import ArtifactProvider
from ai_factory.artifact_pipeline import (
    GeneratedArtifact,
    generate_requested_artifacts,
)


def run_artifact_generation(
    project_root: Path,
    agent_name: str,
    result: AgentResult,
    context: dict[str, Any],
    provider: ArtifactProvider,
) -> list[GeneratedArtifact]:
    """Generate artifacts requested by a completed agent."""

    if not result.artifact_requests:
        return []

    return generate_requested_artifacts(
        project_root=project_root,
        agent_name=agent_name,
        requests=result.artifact_requests,
        context=context,
        provider=provider,
    )
