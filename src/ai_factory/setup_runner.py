from dataclasses import dataclass
from pathlib import Path
import subprocess

from ai_factory.setup_command_policy import (
    validate_setup_command,
)


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

    completed = subprocess.run(
        command,
        cwd=project_root,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )

    return SetupExecutionResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
