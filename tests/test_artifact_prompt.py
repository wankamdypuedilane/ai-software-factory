from ai_factory.artifact_prompt import build_artifact_prompt
from ai_factory.artifact_request import ArtifactGenerationTask


def test_build_artifact_prompt_contains_task_details() -> None:
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
        "state": {
            "agents": {
                "product": {
                    "status": "REVIEW_REQUIRED",
                }
            }
        },
        "human_input": (
            "# Product Input\n\n"
            "Build a ride-hailing application."
        ),
    }

    prompt = build_artifact_prompt(
        task,
        context,
    )

    assert "# Artifact Generation" in prompt
    assert "Agent: product" in prompt
    assert "Target path: knowledge/project/vision.md" in prompt
    assert "Document the product vision." in prompt
    assert "Test Project" in prompt
    assert "## Human Input" in prompt
    assert "Build a ride-hailing application." in prompt
    assert (
        "Generate only the content for "
        "`knowledge/project/vision.md`."
        in prompt
    )


def test_build_artifact_prompt_omits_human_input_when_missing() -> None:
    task = ArtifactGenerationTask(
        agent_name="architect",
        path="knowledge/architecture/system.md",
        purpose="Document the system architecture.",
    )

    context = {
        "project": {},
        "state": {},
        "human_input": None,
    }

    prompt = build_artifact_prompt(
        task,
        context,
    )

    assert "## Human Input" not in prompt
    assert "Do not generate any other artifact." in prompt
    assert "Do not invent missing product requirements." in prompt
