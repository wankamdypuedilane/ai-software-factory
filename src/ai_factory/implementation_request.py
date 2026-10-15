from dataclasses import dataclass

from ai_factory.agent_result import AgentImplementationRequest
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)


@dataclass
class ImplementationTask:
    agent_name: str
    id: str
    title: str
    purpose: str
    kind: ImplementationTaskKind | None = None
    scope: ImplementationScope | None = None
    verification: VerificationPolicy | None = None


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
            kind=request.kind,
            scope=request.scope,
            verification=request.verification,
        )
        for request in requests
    ]
