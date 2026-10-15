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


UPSTREAM_INSTRUCTION = (
    "Treat the upstream artifacts as approved decisions; "
    "do not mark as unspecified anything they define."
)


def test_build_artifact_prompt_includes_upstream_artifacts() -> None:
    task = ArtifactGenerationTask(
        agent_name="ux_ui",
        path="knowledge/design/ux-specification.md",
        purpose="Document the CLI UX.",
    )

    context = {
        "project": {},
        "state": {},
        "human_input": None,
        "artifacts": {
            "knowledge/project/requirements.md": (
                "# Requirements\n\nDefault storage is ./todos.json.\n"
            ),
            "workflows/backlog/user-stories.md": (
                "# User Stories\n\nUS-01 Persist todos.\n"
            ),
        },
    }

    prompt = build_artifact_prompt(
        task,
        context,
    )

    assert "## Upstream Artifacts" in prompt
    assert (
        "### knowledge/project/requirements.md\n"
        "# Requirements\n\nDefault storage is ./todos.json."
        in prompt
    )
    assert (
        "### workflows/backlog/user-stories.md\n"
        "# User Stories\n\nUS-01 Persist todos."
        in prompt
    )
    assert UPSTREAM_INSTRUCTION in prompt


def test_build_artifact_prompt_omits_upstream_section_without_artifacts() -> None:
    task = ArtifactGenerationTask(
        agent_name="product",
        path="knowledge/project/vision.md",
        purpose="Document the product vision.",
    )

    for artifacts in (None, {}):
        context = {
            "project": {},
            "state": {},
            "human_input": "Build a todo CLI.",
            "artifacts": artifacts,
        }

        prompt = build_artifact_prompt(
            task,
            context,
        )

        assert "## Upstream Artifacts" not in prompt
        assert UPSTREAM_INSTRUCTION not in prompt
        assert "## Generation Instructions" in prompt

    prompt = build_artifact_prompt(
        task,
        {
            "project": {},
            "state": {},
        },
    )

    assert "## Upstream Artifacts" not in prompt


def test_build_artifact_prompt_orders_upstream_artifacts_before_instructions() -> None:
    task = ArtifactGenerationTask(
        agent_name="architect",
        path="knowledge/architecture/system.md",
        purpose="Document the system architecture.",
    )

    context = {
        "project": {},
        "state": {},
        "human_input": "Prefer the standard library.",
        "artifacts": {
            "knowledge/project/requirements.md": "Requirements.",
            "design/ux-ui/user-flows.md": "User flows.",
        },
    }

    prompt = build_artifact_prompt(
        task,
        context,
    )

    headings = [
        line
        for line in prompt.splitlines()
        if line.startswith("#")
    ]

    assert headings == [
        "# Artifact Generation",
        "## Purpose",
        "## Project Configuration",
        "## Workflow State",
        "## Human Input",
        "## Upstream Artifacts",
        "### knowledge/project/requirements.md",
        "### design/ux-ui/user-flows.md",
        "## Generation Instructions",
    ]

    instructions = prompt.split("## Generation Instructions", 1)[1]

    assert UPSTREAM_INSTRUCTION in instructions
    assert instructions.rstrip().endswith(UPSTREAM_INSTRUCTION)
