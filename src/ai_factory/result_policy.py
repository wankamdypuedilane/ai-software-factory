from ai_factory.agent_result import AgentResult


RESULT_STATUS_TO_AGENT_STATUS = {
    "NEEDS_INPUT": "BLOCKED",
    "BLOCKED": "BLOCKED",
    "REVIEW_REQUIRED": "REVIEW_REQUIRED",
    "COMPLETED": "REVIEW_REQUIRED",
}


def get_agent_status_from_result(
    result: AgentResult,
) -> str:
    """Map an AgentResult status to a Factory workflow status."""

    try:
        return RESULT_STATUS_TO_AGENT_STATUS[
            result.status
        ]
    except KeyError as error:
        raise ValueError(
            f"Unsupported agent result status: {result.status}"
        ) from error
