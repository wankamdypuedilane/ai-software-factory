from ai_factory.blocker_contract import (
    Blocker,
    coerce_blockers,
)
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

    blockers: list[Blocker] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.blockers = coerce_blockers(self.blockers)

    deployment_ready: bool = False

    rollback_strategy: str = ""
