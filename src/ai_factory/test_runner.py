from dataclasses import dataclass
import os
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


DEFAULT_DATABASE_NAME = "factory_local"

DEFAULT_DATABASE_URL_TEMPLATE = (
    "postgresql://user:password@localhost:5432/{database}"
)


def build_default_database_url(
    project_identity: tuple[str, ...] = (),
) -> str:
    """Build the fallback validation database URL for a project.

    The engine knows no project name of its own: the database is named after
    the project under construction, or after a neutral default when the
    identity is unknown.
    """

    database = "_".join(
        part
        for part in project_identity
        if part
    ) or DEFAULT_DATABASE_NAME

    return DEFAULT_DATABASE_URL_TEMPLATE.format(
        database=database,
    )


def run_test_command(
    project_root: Path,
    command: str,
    project_identity: tuple[str, ...] = (),
) -> CommandExecutionResult:
    """Execute one declared test command inside the project."""

    if not command.strip():
        raise ValueError(
            "Test command cannot be empty."
        )

    validate_test_command(
        command
    )

    env = os.environ.copy()

    if not env.get("DATABASE_URL"):
        env["DATABASE_URL"] = build_default_database_url(
            project_identity
        )

    completed = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )

    return CommandExecutionResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
