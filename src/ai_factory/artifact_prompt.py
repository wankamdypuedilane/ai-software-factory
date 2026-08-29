from typing import Any

from ai_factory.artifact_request import ArtifactGenerationTask


def build_artifact_prompt(
    task: ArtifactGenerationTask,
    context: dict[str, Any],
) -> str:
    """Build the prompt used to generate one requested artifact."""

    project = context.get("project", {})
    state = context.get("state", {})
    human_input = context.get("human_input")

    sections = [
        "# Artifact Generation",
        "",
        f"Agent: {task.agent_name}",
        f"Target path: {task.path}",
        "",
        "## Purpose",
        task.purpose,
        "",
        "## Project Configuration",
        repr(project),
        "",
        "## Workflow State",
        repr(state),
    ]

    if human_input:
        sections.extend(
            [
                "",
                "## Human Input",
                human_input.strip(),
            ]
        )

    sections.extend(
        [
            "",
            "## Generation Instructions",
            f"Generate only the content for `{task.path}`.",
            "Do not generate any other artifact.",
            "Do not wrap the result in Markdown code fences.",
            "Do not include commentary before or after the artifact.",
            "Use only information supported by the supplied context.",
            "Do not invent missing product requirements.",
        ]
    )

    return "\n".join(sections)
