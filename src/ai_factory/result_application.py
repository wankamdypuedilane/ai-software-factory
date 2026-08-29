from typing import Any

from ai_factory.agent_result import AgentResult
from ai_factory.result_policy import get_agent_status_from_result


def apply_agent_result(
    state: dict[str, Any],
    agent_name: str,
    result: AgentResult,
) -> dict[str, Any]:
    """Apply an AgentResult to the Factory workflow state."""

    agents = state.get("agents")

    if not isinstance(agents, dict):
        raise ValueError(
            "Factory state does not contain valid agents."
        )

    if agent_name not in agents:
        raise KeyError(
            f"Unknown agent: {agent_name}"
        )

    agent_state = agents[agent_name]

    agent_state["status"] = (
        get_agent_status_from_result(result)
    )

    agent_state["last_result"] = {
        "status": result.status,
        "summary": result.summary,
        "questions": list(result.questions),
        "blockers": list(result.blockers),
        "handoff": result.handoff,
        "artifacts": [
            artifact.path
            for artifact in result.artifacts
        ],
        "artifact_requests": [
            {
                "path": request.path,
                "purpose": request.purpose,
            }
            for request in result.artifact_requests
        ],
        "metadata": dict(result.metadata),
    }

    return state
