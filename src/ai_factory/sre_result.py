from ai_factory.blocker_contract import (
    Blocker,
    coerce_blockers,
)
from dataclasses import dataclass, field


@dataclass
class SREFinding:
    id: str
    title: str
    severity: str
    category: str
    description: str
    recommendation: str
    status: str = "OPEN"


@dataclass
class SREResult:
    summary: str
    passed: bool

    findings: list[SREFinding] = field(
        default_factory=list
    )

    test_commands: list[str] = field(
        default_factory=list
    )

    blockers: list[Blocker] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.blockers = coerce_blockers(self.blockers)

    observability_ready: bool = False

    incident_readiness: bool = False
