import os
import sys
import time
from pathlib import Path

import pytest

from ai_factory.process_runner import TIMEOUT_RETURN_CODE, run_shell_command


def test_output_and_exit_code_are_returned(tmp_path: Path) -> None:
    outcome = run_shell_command(
        f'"{sys.executable}" -c "import sys; print(\'ok\'); sys.exit(3)"',
        cwd=tmp_path,
        env=None,
        timeout=30,
    )

    assert outcome.returncode == 3
    assert outcome.stdout.strip() == "ok"
    assert outcome.timed_out is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_a_child_that_never_exits_does_not_hang_the_factory(tmp_path: Path) -> None:
    # The shell starts a grandchild that keeps the output pipe open forever,
    # like a Node test with an unclosed database pool.
    script = tmp_path / "forever.py"
    script.write_text("import time\nprint('started', flush=True)\ntime.sleep(3600)\n", encoding="utf-8")

    started = time.monotonic()
    outcome = run_shell_command(
        f'"{sys.executable}" "{script}" & wait',
        cwd=tmp_path,
        env=None,
        timeout=2,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 20
    assert outcome.timed_out is True
    assert outcome.returncode == TIMEOUT_RETURN_CODE
    assert "did not finish within 2 seconds" in outcome.stderr
    assert "started" in outcome.stdout
