from ai_factory.blocker_contract import (
    Blocker,
    coerce_blockers,
)
from dataclasses import dataclass, field


@dataclass
class QADefect:
    id: str
    title: str
    severity: str
    related_story: str
    expected: str
    actual: str


@dataclass
class QAResult:
    summary: str
    passed: bool
    defects: list[QADefect] = field(
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
