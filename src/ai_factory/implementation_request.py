from dataclasses import dataclass

from ai_factory.agent_result import AgentImplementationRequest


@dataclass
class ImplementationTask:
    agent_name: str
    id: str
    title: str
    purpose: str


def build_implementation_tasks(
    agent_name: str,
    requests: list[AgentImplementationRequest],
) -> list[ImplementationTask]:
    """Convert agent implementation requests into implementation tasks."""

    return [
        ImplementationTask(
            agent_name=agent_name,
            id=request.id,
            title=request.title,
            purpose=request.purpose,
        )
        for request in requests
    ]
