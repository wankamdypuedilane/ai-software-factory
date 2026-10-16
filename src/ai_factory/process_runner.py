"""Run a shell command with a timeout that really ends it.

`subprocess.run(..., shell=True, timeout=...)` kills only the shell when the
timeout expires, then waits for the output pipes to close. A program the
shell started keeps them open: on Windows a real run waited more than five
hours on a Node test that never exited (an open database handle), and the
whole Factory stood still. Here the command runs in its own process group,
the whole tree is killed on timeout, and the pipes are never waited on
without a bound.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess


PIPE_DRAIN_SECONDS = 10
TIMEOUT_RETURN_CODE = 124


@dataclass
class CommandOutcome:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        process.kill()
    except OSError:
        pass


def run_shell_command(
    command: str,
    cwd: Path,
    env: dict[str, str] | None,
    timeout: float,
) -> CommandOutcome:
    """Run `command` through the shell; never wait past `timeout` + a drain."""

    kwargs: dict = {}

    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return CommandOutcome(process.returncode, stdout or "", stderr or "")
    except subprocess.TimeoutExpired:
        _kill_tree(process)

    try:
        stdout, stderr = process.communicate(timeout=PIPE_DRAIN_SECONDS)
    except subprocess.TimeoutExpired:
        # A descendant escaped the kill and still holds the pipes: stop
        # reading rather than wait forever.
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        stdout, stderr = "", ""

    note = (
        f"\n[Factory: the command did not finish within {int(timeout)} seconds "
        "and was stopped with every process it started. A test that never "
        "exits usually leaves something open: a database pool or client "
        "not closed (pool.end()), a server still listening, a timer or an "
        "interval still running.]"
    )

    return CommandOutcome(
        TIMEOUT_RETURN_CODE,
        stdout or "",
        (stderr or "") + note,
        timed_out=True,
    )
