"""A failing implementation unit must never have existed in the workspace."""

from pathlib import Path

import pytest

from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)
from ai_factory.implementation_request import (
    ImplementationTask,
)
from ai_factory.implementation_result import (
    ImplementationFileChange,
    ImplementationResult,
)
from ai_factory.implementation_runtime import (
    run_implementation_task,
)
from ai_factory.setup_runner import (
    SetupExecutionResult,
)
from ai_factory.test_runner import (
    CommandExecutionResult,
)
from ai_factory.workspace_transaction import (
    load_failed_transaction_snapshot,
)


TASK_ID = "ACME-DEV-APP-MODULE"


class StaticProvider:
    def __init__(
        self,
        result: ImplementationResult,
    ) -> None:
        self.result = result
        self.prompts: list[str] = []

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompts.append(prompt)
        return self.result


def _task() -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id=TASK_ID,
        title="App module",
        purpose="Implement the app module.",
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )


def _seed_workspace(
    root: Path,
) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.ts").write_text(
        "export const app = 'ORIGINAL';\n",
        encoding="utf-8",
    )
    (root / "src" / "untouched.ts").write_text(
        "export const untouched = 'ORIGINAL';\n",
        encoding="utf-8",
    )
    # The unit under test declares `npm test -- src/app.test.ts`, so the
    # target has to exist for that command to validate anything.
    (root / "src" / "app.test.ts").write_text(
        "// covers src/app.ts\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"name":"demo","version":"1.0.0"}',
        encoding="utf-8",
    )


def _stub_commands(
    monkeypatch: pytest.MonkeyPatch,
    *,
    test_returncodes: list[int] | None = None,
    setup_returncode: int = 0,
    on_test=None,
    on_setup=None,
) -> list[tuple[str, str, Path]]:
    """Record every command with the root it ran in.

    `test_returncodes` is consumed in call order, so a baseline run and the
    final run can be given different outcomes. A genuine regression needs a
    passing baseline followed by a failing run: two identical failures are
    a pre-existing failure, which the runtime deliberately tolerates.
    """

    calls: list[tuple[str, str, Path]] = []
    remaining_codes = list(test_returncodes or [])

    def fake_test(**kwargs):
        root = kwargs["project_root"]
        command = kwargs["command"]
        calls.append(("test", command, root))

        if on_test is not None:
            on_test(root, command)

        returncode = (
            remaining_codes.pop(0)
            if remaining_codes
            else 0
        )

        return CommandExecutionResult(
            command=command,
            returncode=returncode,
            stdout="",
            stderr="boom" if returncode else "",
        )

    def fake_setup(**kwargs):
        root = kwargs["project_root"]
        command = kwargs["command"]
        calls.append(("setup", command, root))

        if on_setup is not None:
            on_setup(root, command)

        return SetupExecutionResult(
            command=command,
            returncode=setup_returncode,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_test,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        fake_setup,
    )

    return calls


def _result(
    files: list[ImplementationFileChange],
    tests: list[str] | None = None,
    setup_commands: list[str] | None = None,
) -> ImplementationResult:
    return ImplementationResult(
        task_id=TASK_ID,
        summary="App module implemented.",
        files=files,
        setup_commands=setup_commands or [],
        tests=tests or ["npm test -- src/app.test.ts"],
    )


# --------------------------------------------------------------------------
# FAIL: nothing reaches the real workspace
# --------------------------------------------------------------------------


def test_failing_task_leaves_an_existing_file_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch, test_returncodes=[0, 1])

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
            ]
        )
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert not execution.tests_passed

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const app = 'ORIGINAL';\n"


def test_failing_task_does_not_leave_a_created_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch, test_returncodes=[0, 1])

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/created.ts",
                    content="export const created = true;\n",
                ),
            ]
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert not (
        tmp_path / "src" / "created.ts"
    ).exists()


def test_failing_setup_promotes_no_file_at_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch, setup_returncode=1)

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
                ImplementationFileChange(
                    path="src/created.ts",
                    content="export const created = true;\n",
                ),
            ],
            setup_commands=["npm install --ignore-scripts"],
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const app = 'ORIGINAL';\n"

    assert not (
        tmp_path / "src" / "created.ts"
    ).exists()


def test_failing_task_does_not_leak_a_manifest_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch, test_returncodes=[0, 1])

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="package.json",
                    content='{"name":"demo","version":"2.0.0"}',
                ),
            ]
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert (
        tmp_path / "package.json"
    ).read_text(
        encoding="utf-8",
    ) == '{"name":"demo","version":"1.0.0"}'


def test_failing_task_does_not_leak_generated_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A setup command writing artifacts must not pollute the workspace."""

    _seed_workspace(tmp_path)

    def generate(root: Path, command: str) -> None:
        target = root / "node_modules" / ".prisma" / "client"
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.js").write_text(
            "module.exports = {};\n",
            encoding="utf-8",
        )

    _stub_commands(
        monkeypatch,
        test_returncodes=[0, 1],
        on_setup=generate,
    )

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
            ],
            setup_commands=["npm run prisma:generate"],
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert not (
        tmp_path / "node_modules" / ".prisma"
    ).exists()


def test_rejected_provider_response_still_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch)

    provider = StaticProvider(
        ImplementationResult(
            task_id=TASK_ID,
            summary="Bad JSON.",
            files=[
                ImplementationFileChange(
                    path="package.json",
                    content="{not json",
                ),
            ],
            tests=["npm test -- src/app.test.ts"],
        )
    )

    with pytest.raises(
        ValueError,
        match="Generated JSON file is invalid",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=provider,
        )

    assert (
        tmp_path / "package.json"
    ).read_text(
        encoding="utf-8",
    ) == '{"name":"demo","version":"1.0.0"}'


# --------------------------------------------------------------------------
# PASS: changes are promoted
# --------------------------------------------------------------------------


def test_passing_task_promotes_its_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch)

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
                ImplementationFileChange(
                    path="src/created.ts",
                    content="export const created = true;\n",
                ),
            ]
        )
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert execution.tests_passed

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const app = 'MODIFIED';\n"

    assert (
        tmp_path / "src" / "created.ts"
    ).is_file()

    assert (
        tmp_path / "src" / "untouched.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const untouched = 'ORIGINAL';\n"


def test_passing_task_promotes_a_manifest_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch)

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="package.json",
                    content='{"name":"demo","version":"2.0.0"}',
                ),
            ]
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert (
        tmp_path / "package.json"
    ).read_text(
        encoding="utf-8",
    ) == '{"name":"demo","version":"2.0.0"}'


# --------------------------------------------------------------------------
# Execution happens inside the transaction, in the right order
# --------------------------------------------------------------------------


def test_all_commands_run_inside_the_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)

    calls = _stub_commands(monkeypatch)

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
            ],
            setup_commands=["npm install --ignore-scripts"],
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert calls

    for kind, command, root in calls:
        assert root != tmp_path, (
            f"{kind} command ran in the real workspace: {command}"
        )


def test_baseline_runs_before_the_implementation_is_applied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)

    observed: list[str] = []

    def record(root: Path, command: str) -> None:
        observed.append(
            (root / "src" / "app.ts").read_text(
                encoding="utf-8",
            )
        )

    _stub_commands(
        monkeypatch,
        on_test=record,
    )

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
            ]
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    assert observed == [
        "export const app = 'ORIGINAL';\n",
        "export const app = 'MODIFIED';\n",
    ]


# --------------------------------------------------------------------------
# Diagnostics survive the rollback
# --------------------------------------------------------------------------


def test_failure_diagnostics_survive_the_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch, test_returncodes=[0, 1])

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
            ]
        )
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=provider,
    )

    # Test output is still available for the retry.
    assert [
        item.command
        for item in execution.test_results
    ] == ["npm test -- src/app.test.ts"]

    assert execution.test_results[0].stderr == "boom"

    assert [
        item.command
        for item in execution.baseline_test_results
    ] == ["npm test -- src/app.test.ts"]

    # The attempted content is preserved outside the workspace tree.
    snapshot = load_failed_transaction_snapshot(
        tmp_path,
        TASK_ID,
    )

    assert snapshot == {
        "src/app.ts": "export const app = 'MODIFIED';\n",
    }


def test_retry_prompt_still_shows_the_failed_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_workspace(tmp_path)
    _stub_commands(monkeypatch, test_returncodes=[0, 1])

    failing = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'BROKEN';\n",
                ),
            ]
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=failing,
    )

    _stub_commands(monkeypatch)

    retrying = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'FIXED';\n",
                ),
            ]
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=retrying,
        retry_test_results=[
            {
                "command": "npm test -- src/app.test.ts",
                "passed": False,
                "stdout": "",
                "stderr": "src/app.ts:1:1 error",
            }
        ],
    )

    prompt = retrying.prompts[0]

    assert "## Previous Failed Attempt" in prompt
    assert "export const app = 'BROKEN';" in prompt

    # The real workspace state is still shown as it truly is.
    assert "export const app = 'ORIGINAL';" in prompt


def test_concurrent_workspace_write_aborts_the_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An external edit under a promoted file must not be overwritten."""

    from ai_factory.workspace_transaction import (
        PromotionConflictError,
    )

    _seed_workspace(tmp_path)

    def concurrent_write(root: Path, command: str) -> None:
        (tmp_path / "src" / "app.ts").write_text(
            "export const app = 'EXTERNAL';\n",
            encoding="utf-8",
        )

    _stub_commands(
        monkeypatch,
        on_test=concurrent_write,
    )

    provider = StaticProvider(
        _result(
            [
                ImplementationFileChange(
                    path="src/app.ts",
                    content="export const app = 'MODIFIED';\n",
                ),
                ImplementationFileChange(
                    path="src/created.ts",
                    content="export const created = true;\n",
                ),
            ]
        )
    )

    with pytest.raises(
        PromotionConflictError,
        match="src/app.ts",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=_task(),
            context={},
            provider=provider,
        )

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const app = 'EXTERNAL';\n"

    assert not (
        tmp_path / "src" / "created.ts"
    ).exists()
