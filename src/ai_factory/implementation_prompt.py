from typing import Any

from ai_factory.implementation_request import ImplementationTask


def build_implementation_prompt(
    task: ImplementationTask,
    context: dict[str, Any],
) -> str:
    """Build a focused prompt for one implementation task."""

    project = context.get("project", {})
    state = context.get("state", {})
    artifacts = context.get("artifacts", {})
    human_input = context.get("human_input")

    sections = [
        "# Implementation Task",
        "",
        f"Agent: {task.agent_name}",
        f"Task ID: {task.id}",
        f"Title: {task.title}",
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

    if artifacts:
        sections.extend(
            [
                "",
                "## Relevant Artifacts",
            ]
        )

        for path, content in artifacts.items():
            sections.extend(
                [
                    "",
                    f"### {path}",
                    content.strip(),
                ]
            )

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
            "## Implementation Instructions",
            "Work only on this implementation task.",
            "Respect the approved architecture and selected technologies.",
            "Respect the approved UX/UI specifications.",
            "Include the automated tests required for this task.",
            "Do not implement unrelated features.",
            "Do not introduce architectural changes unless explicitly required.",
            "Report blockers instead of inventing missing requirements.",
        ]
    )

    return "\n".join(sections)
