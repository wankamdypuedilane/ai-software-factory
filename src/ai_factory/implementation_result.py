from dataclasses import dataclass, field

from ai_factory.blocker_contract import (
    Blocker,
    coerce_blockers,
)


@dataclass
class ImplementationFileChange:
    path: str
    content: str
    operation: str = "write"


@dataclass
class ImplementationResult:
    task_id: str
    summary: str
    files: list[ImplementationFileChange] = field(
        default_factory=list
    )
    setup_commands: list[str] = field(
        default_factory=list
    )
    tests: list[str] = field(
        default_factory=list
    )
    blockers: list[Blocker] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.blockers = coerce_blockers(self.blockers)
