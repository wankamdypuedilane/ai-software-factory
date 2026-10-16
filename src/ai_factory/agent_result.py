from dataclasses import dataclass, field
from typing import Any

from ai_factory.blocker_contract import (
    Blocker,
    coerce_blockers,
)
from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)


@dataclass
class AgentArtifact:
    path: str
    content: str


@dataclass
class AgentArtifactRequest:
    path: str
    purpose: str


@dataclass
class AgentImplementationRequest:
    id: str
    title: str
    purpose: str
    kind: ImplementationTaskKind | None = None
    scope: ImplementationScope | None = None
    verification: VerificationPolicy | None = None


@dataclass
class AgentResult:
    status: str
    summary: str
    artifacts: list[AgentArtifact] = field(default_factory=list)
    artifact_requests: list[AgentArtifactRequest] = field(
        default_factory=list
    )
    implementation_requests: list[
        AgentImplementationRequest
    ] = field(
        default_factory=list
    )
    questions: list[str] = field(default_factory=list)
    # The same questions with answer options, so an interface can offer a
    # recommended choice instead of a blank text box. Each entry:
    # {"question", "why", "options": [{"label", "detail", "recommended"}]}.
    question_details: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    handoff: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Legacy prose from an old state stays readable.
        self.blockers = coerce_blockers(self.blockers)
