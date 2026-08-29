from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentArtifact:
    path: str
    content: str


@dataclass
class AgentArtifactRequest:
    path: str
    purpose: str


@dataclass
class AgentResult:
    status: str
    summary: str
    artifacts: list[AgentArtifact] = field(default_factory=list)
    artifact_requests: list[AgentArtifactRequest] = field(
        default_factory=list
    )
    questions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    handoff: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
