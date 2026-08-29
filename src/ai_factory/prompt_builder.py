import json
from typing import Any


def build_agent_prompt(
    context: dict[str, Any],
) -> str:
    """Build a deterministic text prompt from an agent execution context."""

    agent_name = context["agent_name"]
    contract = context["contract"]
    project = context["project"]
    state = context["state"]
    artifacts = context.get("artifacts", {})

    sections = [
        f"# AI Software Factory Agent Execution",
        "",
        f"Agent: {agent_name}",
        "",
        "## Agent Contract",
        contract.strip(),
        "",
        "## Project Configuration",
        json.dumps(
            project,
            indent=2,
            ensure_ascii=False,
        ),
        "",
        "## Workflow State",
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
    ]

    if artifacts:
        sections.extend(
            [
                "",
                "## Context Artifacts",
            ]
        )

        for artifact_path, artifact_content in artifacts.items():
            sections.extend(
                [
                    "",
                    f"### {artifact_path}",
                    artifact_content.strip(),
                ]
            )

    sections.extend(
        [
            "",
            "## Execution Instruction",
            (
                "Execute the responsibilities defined in the Agent Contract "
                "using only the supplied project context and artifacts. "
                "Do not invent project requirements that are not supported "
                "by the supplied context."
            ),
        ]
    )

    return "\n".join(sections)
