from dataclasses import dataclass

from ai_factory.agent_result import AgentArtifactRequest


@dataclass
class ArtifactGenerationTask:
    agent_name: str
    path: str
    purpose: str


def build_artifact_generation_tasks(
    agent_name: str,
    requests: list[AgentArtifactRequest],
) -> list[ArtifactGenerationTask]:
    """Convert agent artifact requests into generation tasks."""

    return [
        ArtifactGenerationTask(
            agent_name=agent_name,
            path=request.path,
            purpose=request.purpose,
        )
        for request in requests
    ]
