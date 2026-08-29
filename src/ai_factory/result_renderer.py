from ai_factory.agent_result import AgentResult


def render_agent_result(
    agent_name: str,
    result: AgentResult,
) -> str:
    """Render an AgentResult as readable terminal output."""

    lines = [
        f"Agent: {agent_name}",
        f"Status: {result.status}",
        "",
        "Summary:",
        result.summary,
    ]

    if result.questions:
        lines.extend(
            [
                "",
                "Questions:",
            ]
        )

        for question in result.questions:
            lines.append(
                f"- {question}"
            )

    if result.blockers:
        lines.extend(
            [
                "",
                "Blockers:",
            ]
        )

        for blocker in result.blockers:
            lines.append(
                f"- {blocker}"
            )

    if result.artifacts:
        lines.extend(
            [
                "",
                "Artifacts:",
            ]
        )

        for artifact in result.artifacts:
            lines.append(
                f"- {artifact.path}"
            )

    lines.extend(
        [
            "",
            "Handoff: "
            + (
                result.handoff
                if result.handoff
                else "none"
            ),
        ]
    )

    return "\n".join(lines)
