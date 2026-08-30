from dataclasses import dataclass, field


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
    tests: list[str] = field(
        default_factory=list
    )
    blockers: list[str] = field(
        default_factory=list
    )
