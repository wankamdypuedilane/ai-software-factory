from dataclasses import dataclass
from pathlib import Path
import subprocess

from ai_factory.test_command_policy import (
    validate_test_command,
)


@dataclass
class CommandExecutionResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_test_command(
    project_root: Path,
    command: str,
) -> CommandExecutionResult:
    """Execute one declared test command inside the project."""

    if not command.strip():
        raise ValueError(
            "Test command cannot be empty."
        )

    validate_test_command(
        command
    )

    completed = subprocess.run(
        command,
        cwd=project_root,
        shell=True,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    return CommandExecutionResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
