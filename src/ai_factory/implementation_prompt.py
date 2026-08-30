from typing import Any

from ai_factory.implementation_request import ImplementationTask


def build_implementation_prompt(
    task: ImplementationTask,
    context: dict[str, Any],
    retry_test_results: list[dict[str, Any]] | None = None,
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

    if retry_test_results:
        sections.extend(
            [
                "",
                "## Previous Test Failures",
            ]
        )

        for test_result in retry_test_results:
            command = test_result.get(
                "command",
                "",
            )
            returncode = test_result.get(
                "returncode",
                "",
            )
            stdout = test_result.get(
                "stdout",
                "",
            )
            stderr = test_result.get(
                "stderr",
                "",
            )

            sections.extend(
                [
                    "",
                    f"Command: {command}",
                    f"Return code: {returncode}",
                    "",
                    "### stdout",
                    str(stdout).strip(),
                    "",
                    "### stderr",
                    str(stderr).strip(),
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
            "Fix the existing implementation when previous test failures are supplied.",
            "Do not implement unrelated features.",
            "Do not introduce architectural changes unless explicitly required.",
            "Report blockers instead of inventing missing requirements.",
        ]
    )

    return "\n".join(sections)
