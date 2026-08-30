import json
from typing import Any


def get_agent_specific_instruction(
    agent_name: str,
) -> str | None:
    """Return additional execution guidance for a specific agent."""

    if agent_name == "developer":
        return (
            "Do not generate the entire application implementation in this "
            "agent result. Instead, produce concise implementation_requests "
            "that break the approved work into small, independently "
            "implementable units. Base those requests on approved User "
            "Stories, acceptance criteria, UX/UI specifications, architecture, "
            "and selected technologies. Each implementation request must have "
            "a stable id, a concise title, and a clear purpose. "
            "Do not invent features outside the approved scope."
        )

    return None


def build_agent_prompt(
    context: dict[str, Any],
) -> str:
    """Build a deterministic text prompt from an agent execution context."""

    agent_name = context["agent_name"]
    contract = context["contract"]
    project = context["project"]
    state = context["state"]
    artifacts = context.get("artifacts", {})
    human_input = context.get("human_input")

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

    if human_input:
        sections.extend(
            [
                "",
                "## Human Input",
                human_input.strip(),
            ]
        )

    agent_specific_instruction = get_agent_specific_instruction(
        agent_name
    )

    if agent_specific_instruction:
        sections.extend(
            [
                "",
                "## Agent-Specific Instruction",
                agent_specific_instruction,
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
