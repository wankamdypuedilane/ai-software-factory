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
    blockers: list[str] = field(
        default_factory=list
    )
