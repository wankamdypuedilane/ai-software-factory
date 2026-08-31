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

    blockers: list[str] = field(
        default_factory=list
    )

    observability_ready: bool = False

    incident_readiness: bool = False
