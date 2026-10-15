from typing import Any

from ai_factory.validation_context import (
    VALIDATION_EXECUTION_RULES,
)


MAX_QA_ARTIFACT_CHARS = 8000
MAX_QA_ARTIFACTS_TOTAL_CHARS = 40000


def _artifact_sections(
    artifacts: dict[str, Any],
) -> list[str]:
    """Return the approved artifacts within the QA budget."""

    sections: list[str] = []
    used = 0

    for path, content in artifacts.items():
        if used >= MAX_QA_ARTIFACTS_TOTAL_CHARS:
            sections.append(
                "[further artifacts omitted to stay within the budget]"
            )
            break

        if not isinstance(content, str):
            continue

        limit = min(
            MAX_QA_ARTIFACT_CHARS,
            MAX_QA_ARTIFACTS_TOTAL_CHARS - used,
        )
        text = content.strip()

        if len(text) > limit:
            text = (
                text[:limit]
                + f"\n[truncated: {len(text) - limit} characters omitted]"
            )

        sections.extend(["", f"### {path}", text])
        used += len(text)

    return sections


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
    ]

    # Requirements and acceptance criteria live in the approved artifacts
    # (requirements, user stories, UX/UI and API contracts). Without them
    # the sections above are empty and QA has nothing to validate against.
    artifacts = context.get("artifacts", {})

    if isinstance(artifacts, dict) and artifacts:
        sections.extend(
            [
                "",
                "## Approved Artifacts",
                "Requirements, acceptance criteria and contracts to "
                "validate against.",
            ]
        )
        sections.extend(_artifact_sections(artifacts))

    human_input = context.get("human_input")

    if isinstance(human_input, str) and human_input.strip():
        sections.extend(["", "## Human Input", human_input.strip()])

    sources = context.get("implemented_sources", {})

    if isinstance(sources, dict) and sources:
        sections.extend(["", "## Implemented Sources"])

        for path, content in sources.items():
            sections.extend(["", f"### {path}", str(content)])

    executed_tests = context.get("executed_tests", [])

    if isinstance(executed_tests, list) and executed_tests:
        sections.extend(
            [
                "",
                "## Tests Already Executed By The Factory",
                repr(executed_tests),
            ]
        )

    sections.extend(
        [
            "",
            "## Execution",
            *(f"- {rule}" for rule in VALIDATION_EXECUTION_RULES),
        ]
    )

    sections += [
        "",
        "## Instructions",
        "- Identify functional defects and regressions.",
        "- Check every available acceptance criterion.",
        "- Propose executable test commands when appropriate.",
        "- Report blockers when validation cannot be completed.",
        "- Use only Critical, High, Medium, or Low severity.",
        "- Do not modify the implementation.",
        "- Return the test commands that validate the acceptance criteria, "
        "for example the project's full test suite.",
        "- Return an independent QA verdict.",
    ]

    return "\n".join(sections)
