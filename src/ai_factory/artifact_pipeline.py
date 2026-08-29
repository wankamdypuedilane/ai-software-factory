from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_factory.agent_result import AgentArtifactRequest
from ai_factory.artifact_generator import (
    ArtifactProvider,
    generate_artifact,
)
from ai_factory.artifact_request import (
    build_artifact_generation_tasks,
)
from ai_factory.artifact_writer import write_artifact


@dataclass
class GeneratedArtifact:
    path: str
    absolute_path: Path


def generate_requested_artifacts(
    project_root: Path,
    agent_name: str,
    requests: list[AgentArtifactRequest],
    context: dict[str, Any],
    provider: ArtifactProvider,
) -> list[GeneratedArtifact]:
    """Generate and write requested artifacts one at a time."""

    tasks = build_artifact_generation_tasks(
        agent_name=agent_name,
        requests=requests,
    )

    generated = []

    for task in tasks:
        content = generate_artifact(
            task=task,
            context=context,
            provider=provider,
        )

        absolute_path = write_artifact(
            project_root=project_root,
            artifact_path=task.path,
            content=content,
        )

        generated.append(
            GeneratedArtifact(
                path=task.path,
                absolute_path=absolute_path,
            )
        )

    return generated
