"""Environment variables stored with a project for its test commands.

Tests used to see only the variables of the shell that started the Factory.
A real run lost TEST_DATABASE_URL when the server was restarted from another
PowerShell window, and the Developer stopped on a blocker it could not fix.
A project can now keep them in `.factory/environment.env` (KEY=VALUE lines,
`#` comments). They apply to every test command run for that project, and
take precedence over the shell, because they were set for this project.
The file lives under `.factory`, which the web interface never exposes.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import re
from typing import Iterator


ENVIRONMENT_FILE = Path(".factory") / "environment.env"

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_active: ContextVar[dict[str, str]] = ContextVar(
    "ai_factory_project_environment",
    default={},
)


def load_project_environment(project_root: Path) -> dict[str, str]:
    """Read the project's stored variables; ignore malformed lines."""

    path = project_root / ENVIRONMENT_FILE

    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}

    values: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        if _NAME.match(name):
            values[name] = value

    return values


@contextmanager
def project_environment(project_root: Path) -> Iterator[dict[str, str]]:
    """Make the project's variables visible to test commands in this run."""

    values = load_project_environment(project_root)
    token = _active.set(values)

    try:
        yield values
    finally:
        _active.reset(token)


def active_project_environment() -> dict[str, str]:
    return dict(_active.get())
