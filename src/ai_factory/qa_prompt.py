from typing import Any


def build_qa_prompt(
    context: dict[str, Any],
) -> str:
    """Build the prompt used for independent QA validation."""

    project = context.get(
        "project",
        {},
    )

    developer = context.get(
        "developer",
        {},
    )

    requirements = context.get(
        "requirements",
        [],
    )

    acceptance_criteria = context.get(
        "acceptance_criteria",
        [],
    )

    architecture = context.get(
        "architecture",
        {},
    )

    implemented_files = developer.get(
        "implemented_files",
        [],
    )

    implementation_results = developer.get(
        "implementation_results",
        [],
    )

    sections = [
        "# QA Validation",
        "",
        "You are the independent QA Agent.",
        "",
        "Validate the implemented software against the "
        "approved requirements and acceptance criteria.",
        "",
        "Do not assume that the implementation is correct "
        "because the Developer reported success.",
        "",
        "## Project",
        repr(project),
        "",
        "## Requirements",
        repr(requirements),
        "",
        "## Acceptance Criteria",
        repr(acceptance_criteria),
        "",
        "## Architecture",
        repr(architecture),
        "",
        "## Developer Implementation",
        repr(implementation_results),
        "",
        "## Implemented Files",
        repr(implemented_files),
        "",
        "## Instructions",
        "- Identify functional defects and regressions.",
        "- Check every available acceptance criterion.",
        "- Propose executable test commands when appropriate.",
        "- Report blockers when validation cannot be completed.",
        "- Use only Critical, High, Medium, or Low severity.",
        "- Do not modify the implementation.",
        "- Return an independent QA verdict.",
    ]

    return "\n".join(sections)
