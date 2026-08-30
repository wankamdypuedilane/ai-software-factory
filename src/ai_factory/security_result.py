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
    blockers: list[str] = field(
        default_factory=list
    )
