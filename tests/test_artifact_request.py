from ai_factory.agent_result import AgentArtifactRequest
from ai_factory.artifact_request import (
    ArtifactGenerationTask,
    build_artifact_generation_tasks,
)


def test_build_artifact_generation_tasks() -> None:
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

    tasks = build_artifact_generation_tasks(
        agent_name="product",
        requests=requests,
    )

    assert len(tasks) == 2

    assert isinstance(
        tasks[0],
        ArtifactGenerationTask,
    )

    assert tasks[0].agent_name == "product"
    assert tasks[0].path == "knowledge/project/vision.md"
    assert tasks[0].purpose == "Document the product vision."

    assert tasks[1].agent_name == "product"
    assert tasks[1].path == "knowledge/project/requirements.md"
    assert tasks[1].purpose == "Document the MVP requirements."


def test_build_artifact_generation_tasks_returns_empty_list() -> None:
    tasks = build_artifact_generation_tasks(
        agent_name="product",
        requests=[],
    )

    assert tasks == []
