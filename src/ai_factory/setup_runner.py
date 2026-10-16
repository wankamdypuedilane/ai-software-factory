from dataclasses import dataclass
from pathlib import Path
from ai_factory.process_runner import run_shell_command

from ai_factory.setup_command_policy import (
    validate_setup_command,
)


SETUP_COMMAND_TIMEOUT_SECONDS = 600


@dataclass
class SetupExecutionResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_setup_command(
    project_root: Path,
    command: str,
    approved_native_packages: tuple[str, ...] | list[str] = (),
) -> SetupExecutionResult:
    """Run one validated setup command inside the project."""

    validate_setup_command(
        command,
        approved_native_packages=approved_native_packages,
    )

    completed = run_shell_command(
        command,
        cwd=project_root,
        env=None,
        timeout=SETUP_COMMAND_TIMEOUT_SECONDS,
    )

    return SetupExecutionResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
