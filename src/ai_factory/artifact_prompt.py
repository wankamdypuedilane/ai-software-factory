import json
from typing import Any

from ai_factory.state_digest import digest_state
from ai_factory.artifact_request import ArtifactGenerationTask


def build_artifact_prompt(
    task: ArtifactGenerationTask,
    context: dict[str, Any],
) -> str:
    """Build the prompt used to generate one requested artifact."""

    project = context.get("project", {})
    state = context.get("state", {})
    human_input = context.get("human_input")
    upstream_artifacts = context.get("artifacts") or {}

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
        repr(digest_state(state, task.agent_name)),
    ]

    if human_input:
        sections.extend(
            [
                "",
                "## Human Input",
                human_input.strip(),
            ]
        )

    validation_outcome = context.get("validation_outcome")

    if isinstance(validation_outcome, dict):
        sections.extend(
            [
                "",
                "## Validation Outcome Of This Cycle",
                "This is what the Factory executed and decided in the "
                "current cycle. Report exactly this outcome; it supersedes "
                "any earlier result shown in the workflow state.",
                json.dumps(
                    validation_outcome,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
            ]
        )

    # Without the upstream artifacts the generator only sees the purpose,
    # and reports as unspecified what earlier phases already decided.
    if upstream_artifacts:
        sections.extend(
            [
                "",
                "## Upstream Artifacts",
            ]
        )

        for path, content in upstream_artifacts.items():
            sections.extend(
                [
                    "",
                    f"### {path}",
                    content.strip(),
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

    if upstream_artifacts:
        sections.append(
            "Treat the upstream artifacts as approved decisions; "
            "do not mark as unspecified anything they define."
        )

    return "\n".join(sections)
