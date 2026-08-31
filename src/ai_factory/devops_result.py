from dataclasses import dataclass, field


@dataclass
class DevOpsChange:
    path: str
    description: str
    category: str


@dataclass
class DevOpsResult:
    summary: str
    passed: bool

    changes: list[DevOpsChange] = field(
        default_factory=list
    )

    test_commands: list[str] = field(
        default_factory=list
    )

    blockers: list[str] = field(
        default_factory=list
    )

    deployment_ready: bool = False

    rollback_strategy: str = ""
