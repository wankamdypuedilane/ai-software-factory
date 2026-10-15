from ai_factory.blocker_contract import (
    Blocker,
    coerce_blockers,
)
from dataclasses import dataclass, field


@dataclass
class SecurityFinding:
    id: str
    title: str
    severity: str
    affected_component: str
    description: str
    impact: str
    evidence: str
    recommended_remediation: str
    priority: str
    status: str


@dataclass
class SecurityResult:
    summary: str
    passed: bool
    findings: list[SecurityFinding] = field(
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
