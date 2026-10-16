import json
from typing import Any

from ai_factory.rework import format_rework_request


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


# How many rounds of questions an agent may ask before it has to decide.
# A real run from the web interface showed the Product agent asking the
# same questions again after every answer, so the project never moved.
MAX_QUESTION_ROUNDS = 2

ANSWERS_HEADING = "## Answers"


def answered_questions_rules(
    human_input: str,
) -> list[str]:
    """Rules that stop an agent from asking answered questions again."""

    rounds = human_input.count(ANSWERS_HEADING)

    if rounds < 1:
        return []

    rules = [
        "",
        "## Answered Questions",
        "The project owner already answered the questions listed under "
        "Answers in the Human Input. Treat every answer as a final "
        "decision. Never ask them again, even reworded or split into "
        "smaller questions.",
        "Ask a new question only when it blocks your work and nothing in "
        "the Human Input or the artifacts answers it.",
    ]

    if rounds >= MAX_QUESTION_ROUNDS:
        rules.append(
            f"The owner has already answered {rounds} rounds of questions. "
            "Do not return NEEDS_INPUT and do not ask any question. Decide "
            "every remaining open point yourself with the safest, simplest "
            "option, write those decisions down as explicit assumptions in "
            "your artifacts, and complete your work."
        )

    return rules


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

        sections.extend(answered_questions_rules(human_input))

    rework = context.get("rework_request")

    if isinstance(rework, dict):
        sections.extend(
            [
                "",
                "## Rework Request",
                *format_rework_request(rework),
                "Plan only the implementation_requests needed to fix these "
                "items; do not re-plan work that is already implemented.",
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
