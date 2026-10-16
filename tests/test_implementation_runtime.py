from pathlib import Path

import pytest

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


class FakeImplementationProvider:
    def __init__(
        self,
        result: ImplementationResult,
    ) -> None:
        self.result = result
        self.prompt: str | None = None
        self.prompts: list[str] = []

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompt = prompt
        self.prompts.append(prompt)
        return self.result


def test_run_implementation_task_executes_and_writes_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication with tests.",
    )

    result = ImplementationResult(
        task_id="US-001",
        summary="Authentication implemented.",
        files=[
            ImplementationFileChange(
                path="src/accounts/models.py",
                content="# models",
            ),
            ImplementationFileChange(
                path="tests/test_auth.py",
                content="# tests",
            ),
        ],
        # A unit that writes governed files has to declare what verifies
        # them; the target is the test this unit authors.
        tests=["pytest tests/test_auth.py"],
    )

    provider = FakeImplementationProvider(
        result
    )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
            "human_input": None,
        },
        provider=provider,
    )

    assert execution.result is result
    assert len(execution.written_files) == 2
    assert [item.command for item in execution.test_results] == [
        "pytest tests/test_auth.py"
    ]
    assert execution.tests_passed is True

    assert (
        tmp_path / "src" / "accounts" / "models.py"
    ).exists()

    assert (
        tmp_path / "tests" / "test_auth.py"
    ).exists()

    assert provider.prompt is not None
    assert "Task ID: US-001" in provider.prompt


def test_run_implementation_task_rejects_mismatched_task_id(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id="US-999",
            summary="Wrong task.",
        )
    )

    with pytest.raises(
        ValueError,
        match="task ID does not match",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )


def test_implementation_task_moves_prisma_generate_from_tests_to_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-DISCOVERY-TEST-REPAIR",
        title="Discovery test repair",
        purpose="Repair discovery tests.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Tests repaired.",
            tests=[
                "npm run prisma:generate",
                "npm run typecheck",
            ],
        )
    )

    setup_commands = []
    test_commands = []

    def fake_setup(
        project_root: Path,
        command: str,
        **_,
    ) -> SetupExecutionResult:
        setup_commands.append(command)

        return SetupExecutionResult(
            command=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    def fake_test(
        project_root: Path,
        command: str,
        **_,
    ) -> CommandExecutionResult:
        test_commands.append(command)

        return CommandExecutionResult(
            command=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        fake_setup,
    )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_test,
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.tests_passed is True

    assert setup_commands == [
        "npm run prisma:generate",
    ]

    # "Discovery test repair" is a narrow unit, so the runtime captures a
    # baseline before applying the result and runs the command again after.
    assert test_commands == [
        "npm run typecheck",
        "npm run typecheck",
    ]


def test_implementation_task_auto_generates_prisma_client_before_node_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(
        'generator client { provider = "prisma-client-js" }\n',
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"@prisma/client":"6.19.3"}}',
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Discovery tests",
        purpose="Run discovery tests.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Discovery tests prepared.",
            tests=[
                "npm test -- src/app/api/v1/tasks/discovery-api.test.ts",
            ],
        )
    )

    calls = []

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        lambda project_root, command, **_: (
            calls.append(("setup", command))
            or SetupExecutionResult(
                command=command,
                returncode=0,
                stdout="",
                stderr="",
            )
        ),
    )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda project_root, command, **_: (
            calls.append(("test", command))
            or CommandExecutionResult(
                command=command,
                returncode=0,
                stdout="",
                stderr="",
            )
        ),
    )

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    # "Discovery tests" is a narrow unit, so its baseline runs first, before
    # the result is applied and before prisma client generation.
    assert calls == [
        (
            "test",
            "npm test -- src/app/api/v1/tasks/discovery-api.test.ts",
        ),
        ("setup", "npm run prisma:generate"),
        (
            "test",
            "npm test -- src/app/api/v1/tasks/discovery-api.test.ts",
        ),
    ]

    assert not (
        tmp_path / "src"
    ).exists()


def test_run_implementation_task_does_not_write_when_blocked(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-001",
        title="Passenger authentication",
        purpose="Implement authentication.",
    )

    result = ImplementationResult(
        task_id="US-001",
        summary="Implementation blocked.",
        files=[
            ImplementationFileChange(
                path="src/accounts/models.py",
                content="# models",
            ),
        ],
        blockers=[
            "Authentication requirement is ambiguous.",
        ],
    )

    provider = FakeImplementationProvider(
        result
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.result.blockers[0].message == (
        "Authentication requirement is ambiguous."
    )

    assert execution.written_files == []
    assert execution.test_results == []

    # A blocked unit did not succeed. It used to answer True here only
    # because an empty test list was read as a vacuous pass.
    assert execution.execution_succeeded is False

    assert not (
        tmp_path / "src" / "accounts" / "models.py"
    ).exists()


def test_run_implementation_task_executes_declared_tests(
    tmp_path: Path,
) -> None:
    test_file = (
        tmp_path
        / "tests"
        / "test_sample.py"
    )

    test_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_file.write_text(
        "def test_sample():\n"
        "    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="US-010",
        title="Sample test",
        purpose="Validate test execution.",
    )

    result = ImplementationResult(
        task_id="US-010",
        summary="Sample implementation.",
        tests=[
            "python -m pytest tests/test_sample.py -q",
        ],
    )

    provider = FakeImplementationProvider(
        result
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(execution.test_results) == 1
    assert execution.test_results[0].passed is True
    assert execution.tests_passed is True


def test_run_implementation_task_passes_retry_diagnostics_to_prompt(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="US-002",
        title="Ride creation",
        purpose="Implement ride creation.",
    )

    result = ImplementationResult(
        task_id="US-002",
        summary="Ride creation fixed.",
    )

    provider = FakeImplementationProvider(
        result
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
        retry_test_results=[
            {
                "command": (
                    "python -m pytest "
                    "tests/test_rides.py -q"
                ),
                "returncode": 1,
                "passed": False,
                "stdout": "1 failed",
                "stderr": "AssertionError",
            }
        ],
    )

    assert execution.result is result

    assert len(provider.prompts) == 1

    prompt = provider.prompts[0]

    assert "## Previous Test Failures" in prompt
    assert (
        "python -m pytest tests/test_rides.py -q"
        in prompt
    )
    assert "Return code: 1" in prompt
    assert "1 failed" in prompt
    assert "AssertionError" in prompt


def test_run_implementation_task_writes_then_sets_up_then_tests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    order: list[str] = []

    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Create foundation",
        purpose="Create the application foundation.",
    )

    result = ImplementationResult(
        task_id="TASK-001",
        summary="Foundation generated.",
        setup_commands=[
            "npm install --ignore-scripts",
        ],
        tests=[
            "npm test -- tests/foundation.test.ts",
        ],
    )

    provider = FakeImplementationProvider(
        result
    )

    def fake_apply_implementation_result(**kwargs):
        order.append("write")
        return []

    def fake_run_setup_command(**kwargs):
        order.append("setup")
        return SetupExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        )

    def fake_run_test_command(**kwargs):
        order.append("test")
        return CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.apply_implementation_result",
        fake_apply_implementation_result,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        fake_run_setup_command,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_run_test_command,
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert order == [
        "test",
        "write",
        "setup",
        "test",
    ]
    assert len(execution.setup_results) == 1
    assert len(execution.test_results) == 1


def test_run_implementation_task_includes_current_task_files_on_retry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "lib" / "http.ts"
    source.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    source.write_text(
        "export function parseJson() {}",
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="US-002",
        title="Fix HTTP parsing",
        purpose="Fix the failing HTTP parser.",
    )

    result = ImplementationResult(
        task_id="US-002",
        summary="HTTP parsing fixed.",
    )
    provider = FakeImplementationProvider(
        result
    )

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "state": {
                "agents": {
                    "developer": {
                        "last_result": {
                            "implementation_results": [
                                {
                                    "task_id": "US-002",
                                    "files": [
                                        "src/lib/http.ts",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        },
        provider=provider,
        retry_test_results=[
            {
                "command": "npm test",
                "returncode": 1,
                "passed": False,
                "stdout": "failed",
                "stderr": "",
            }
        ],
    )

    assert provider.prompt is not None
    assert "## Current Workspace Files" in provider.prompt
    assert "### src/lib/http.ts" in provider.prompt
    assert "export function parseJson()" in provider.prompt


def test_run_implementation_task_includes_files_from_retry_diagnostics(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "lib" / "http.ts"
    test_source = tmp_path / "src" / "lib" / "http.test.ts"
    source.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    source.write_text(
        "export function parseJson() {}",
        encoding="utf-8",
    )
    test_source.write_text(
        "test('parseJson', () => {})",
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="US-002",
        title="Fix HTTP parsing",
        purpose="Fix the failing HTTP parser.",
    )
    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id="US-002",
            summary="HTTP parsing fixed.",
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "state": {
                "agents": {
                    "developer": {
                        "last_result": {
                            "implementation_results": [
                                {
                                    "task_id": "US-002",
                                    "files": [
                                        "src/lib/http.ts",
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        },
        provider=provider,
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 1,
                "passed": False,
                "stdout": (
                    "src/lib/http.test.ts(35,47): "
                    "error TS2322"
                ),
                "stderr": "",
            }
        ],
    )

    assert provider.prompt is not None
    assert "### src/lib/http.ts" in provider.prompt
    assert "### src/lib/http.test.ts" in provider.prompt


def test_run_implementation_task_validates_setup_before_writing(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Persistence",
        purpose="Add persistence.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id="TASK-001",
            summary="Persistence generated.",
            files=[
                ImplementationFileChange(
                    path="prisma/schema.prisma",
                    content="generator client {}",
                )
            ],
            setup_commands=[
                "npm install --ignore-scripts prisma @prisma/client"
            ],
        )
    )

    # The command carries package names, so it matches no allowlist entry.
    # It is now offered a bounded correction first, then refused cleanly.
    with pytest.raises(
        ValueError,
        match="not allowed by the Factory command policy",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )

    assert not (
        tmp_path / "prisma" / "schema.prisma"
    ).exists()


def test_run_implementation_task_includes_existing_package_manifest(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"zod":"3.24.1"}}',
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Add persistence",
        purpose="Add persistence.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id="TASK-001",
            summary="Persistence implemented.",
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert provider.prompt is not None
    assert "### package.json" in provider.prompt
    assert '"zod":"3.24.1"' in provider.prompt


def test_run_implementation_task_limits_retry_diagnostic_files(
    tmp_path: Path,
) -> None:
    relevant_files = [
        "src/modules/tasks/task-repository.ts",
        "src/modules/tasks/task-repository.test.ts",
        "src/modules/tasks/repository.ts",
    ]

    unrelated_files = [
        "src/modules/identity/auth.test.ts",
        "src/modules/identity/session-service.test.ts",
        "src/modules/identity/rate-limit.test.ts",
        "src/lib/prisma.test.ts",
        "src/lib/http.test.ts",
        "src/app/api/v1/auth/register/route.ts",
        "src/app/api/v1/auth/sign-in/route.ts",
        "src/app/api/v1/auth/sign-out/route.ts",
    ]

    for relative_path in (
        relevant_files + unrelated_files
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            f"// {relative_path}",
            encoding="utf-8",
        )

    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Repair task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository repaired.",
        )
    )

    diagnostic_output = "\n".join(
        relevant_files + unrelated_files
    )

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "state": {
                "agents": {
                    "developer": {
                        "last_result": {
                            "implementation_results": [],
                        }
                    }
                }
            }
        },
        provider=provider,
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 2,
                "passed": False,
                "stdout": diagnostic_output,
                "stderr": "",
            }
        ],
    )

    assert provider.prompt is not None

    assert (
        "### src/modules/tasks/task-repository.ts"
        in provider.prompt
    )
    assert (
        "### src/modules/tasks/task-repository.test.ts"
        in provider.prompt
    )
    assert (
        "### src/modules/tasks/repository.ts"
        in provider.prompt
    )

    workspace_section = provider.prompt.split(
        "## Current Workspace Files",
        1,
    )[1].split(
        "## Previous Test Failures",
        1,
    )[0]

    workspace_headings = [
        line
        for line in workspace_section.splitlines()
        if line.startswith("### ") and line != "### Export Index"
    ]

    assert len(workspace_headings) <= 8


def test_retry_does_not_blame_task_for_preexisting_global_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Repair task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository repaired.",
            tests=[
                "npm run typecheck",
            ],
        )
    )

    calls = []

    def fake_run_test_command(
        *,
        project_root,
        command,
        **_,
    ):
        calls.append(command)

        return CommandExecutionResult(
            command=command,
            returncode=2,
            stdout=(
                "src/modules/identity/domain/"
                "credentials.ts(72,64): error TS2554"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_run_test_command,
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.tests_passed


def test_run_implementation_task_rejects_invalid_json_before_writing(
    tmp_path: Path,
) -> None:
    original = '{"name":"taskflow"}'

    package_json = tmp_path / "package.json"
    package_json.write_text(
        original,
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="TASK-001",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id="TASK-001",
            summary="Repository implemented.",
            files=[
                ImplementationFileChange(
                    path="package.json",
                    content=(
                        '{"name":"taskflow"}'
                        " trailing"
                    ),
                ),
            ],
            # Declared so the response reaches the JSON check this test is
            # about, instead of stopping at the missing-validation check.
            tests=["npm run typecheck"],
        )
    )

    with pytest.raises(
        ValueError,
        match="Generated JSON file is invalid",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )

    assert (
        package_json.read_text(
            encoding="utf-8",
        )
        == original
    )


def test_intermediate_task_rejects_full_project_test_suite(
    tmp_path: Path,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository implemented.",
            tests=[
                "npm test",
            ],
        )
    )

    with pytest.raises(
        ValueError,
        match="Full-project test suite is not allowed",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )


def test_intermediate_task_accepts_targeted_test_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    # The targeted command needs an existing target: this test is about the
    # scope policy accepting the command, not about validating nothing.
    target = tmp_path / "src" / "modules" / "tasks"
    target.mkdir(parents=True)
    (target / "task-repository.test.ts").write_text(
        "// covers the task repository\n",
        encoding="utf-8",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository implemented.",
            tests=[
                (
                    "npm test -- "
                    "src/modules/tasks/task-repository.test.ts"
                ),
            ],
        )
    )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.tests_passed


def test_run_implementation_task_ignores_preexisting_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    result = ImplementationResult(
        task_id=task.id,
        summary="Task repository implemented.",
        tests=[
            "npm run typecheck",
        ],
    )

    provider = FakeImplementationProvider(result)

    call_count = 0

    def fake_run_test_command(
        project_root: Path,
        command: str,
        **_,
    ) -> CommandExecutionResult:
        nonlocal call_count
        call_count += 1

        return CommandExecutionResult(
            command=command,
            returncode=2,
            stdout=(
                "src/modules/identity/domain/"
                "credentials.ts(72,64): error TS2554"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        fake_run_test_command,
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "project": {},
            "state": {},
            "artifacts": {},
            "human_input": None,
        },
        provider=provider,
    )

    assert call_count == 2
    assert execution.tests_passed is True


def test_run_implementation_task_detects_new_test_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository implemented.",
            tests=[
                "npm run typecheck",
            ],
        )
    )

    results = [
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=0,
            stdout="",
            stderr="",
        ),
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout="src/modules/tasks/repository.ts: error TS1205",
            stderr="",
        ),
    ]

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: results.pop(0),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.tests_passed is False


def test_run_implementation_task_detects_additional_failure_on_existing_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository implemented.",
            tests=[
                "npm run typecheck",
            ],
        )
    )

    results = [
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout=(
                "src/modules/identity/domain/"
                "credentials.ts: error TS2554"
            ),
            stderr="",
        ),
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout=(
                "src/modules/identity/domain/"
                "credentials.ts: error TS2554\n"
                "src/modules/tasks/repository.ts: error TS1205"
            ),
            stderr="",
        ),
    ]

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: results.pop(0),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.tests_passed is False


def test_retry_task_must_fix_supplied_previous_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Repair the failing task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository repaired.",
            tests=[
                "npm run typecheck",
            ],
        )
    )

    failure_output = (
        "src/modules/tasks/task-repository.test.ts: "
        "error TS2305"
    )

    results = [
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout=failure_output,
            stderr="",
        ),
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout=failure_output,
            stderr="",
        ),
    ]

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: results.pop(0),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 2,
                "passed": False,
                "stdout": failure_output,
                "stderr": "",
            }
        ],
    )

    assert execution.tests_passed is False


def test_retry_task_passes_when_supplied_previous_failure_is_fixed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Repair the failing task repository.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Repository repaired.",
            tests=["npm run typecheck"],
        )
    )

    results = [
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout="src/modules/tasks/task-repository.test.ts: error TS2305",
            stderr="",
        ),
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=0,
            stdout="",
            stderr="",
        ),
    ]

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: results.pop(0),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 2,
                "passed": False,
                "stdout": (
                    "src/modules/tasks/"
                    "task-repository.test.ts: error TS2305"
                ),
                "stderr": "",
            }
        ],
    )

    assert execution.tests_passed is True


def test_retry_task_ignores_unrelated_preexisting_failure_in_same_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-API-LIST-CREATE",
        title="Task API list/create",
        purpose="Implement task list and create APIs.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Task API implemented.",
            tests=[
                "npm run typecheck",
            ],
        )
    )

    unrelated_failure = (
        "src/modules/tasks/task-repository.test.ts: "
        "error TS2305"
    )

    results = [
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout=unrelated_failure,
            stderr="",
        ),
        CommandExecutionResult(
            command="npm run typecheck",
            returncode=2,
            stdout=unrelated_failure,
            stderr="",
        ),
    ]

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: results.pop(0),
    )

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 2,
                "passed": False,
                "stdout": unrelated_failure,
                "stderr": "",
            }
        ],
    )

    assert execution.tests_passed is True


def test_implementation_task_rejects_speculative_workspace_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-DISCOVERY",
        title="Task discovery",
        purpose="Implement task discovery.",
    )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Discovery implemented.",
            tests=["npm run typecheck"],
            blockers=[
                {
                    "message": (
                        "src/app/api/v1/tasks/_helpers.ts may expose a "
                        "different authenticated-user helper name."
                    ),
                    "kind": "INFORMATION",
                    "scope": "WORKSPACE",
                    "fixable_by_agent": True,
                    "requires_human_input": False,
                    "blocking": True,
                },
            ],
        )
    )

    # A speculative workspace note cannot stop the unit, whatever it claims.
    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.result.blockers[0].blocking is False
    assert execution.tests_passed is True


def test_retry_prompt_includes_local_import_dependencies(
    tmp_path: Path,
) -> None:
    route = (
        tmp_path
        / "src"
        / "app"
        / "api"
        / "v1"
        / "tasks"
        / "route.ts"
    )
    domain = (
        tmp_path
        / "src"
        / "modules"
        / "tasks"
        / "domain.ts"
    )

    route.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    domain.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    route.write_text(
        (
            'import { taskPatchSchema } '
            'from "@/modules/tasks/domain";\n'
        ),
        encoding="utf-8",
    )

    domain.write_text(
        (
            "export const taskPatchSchema = {};\n"
            "export const taskCreateSchema = {};\n"
        ),
        encoding="utf-8",
    )

    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-DISCOVERY-ROUTE-ALIGNMENT",
        title="Discovery route alignment",
        purpose="Align task discovery routes.",
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Routes aligned.",
        )
    )

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "state": {
                "agents": {
                    "developer": {
                        "last_result": {
                            "implementation_results": [
                                {
                                    "task_id": task.id,
                                    "files": [
                                        (
                                            "src/app/api/v1/"
                                            "tasks/route.ts"
                                        ),
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        },
        provider=provider,
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "returncode": 2,
                "passed": False,
                "stdout": (
                    "src/app/api/v1/tasks/route.ts"
                    "(7,3): error TS2305"
                ),
                "stderr": "",
            }
        ],
    )

    assert provider.prompt is not None

    assert (
        "### src/app/api/v1/tasks/route.ts"
        in provider.prompt
    )

    assert (
        "### src/modules/tasks/domain.ts"
        in provider.prompt
    )

    assert (
        "export const taskCreateSchema"
        in provider.prompt
    )


def test_implementation_task_rejects_local_fixable_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-DISCOVERY-VERIFICATION",
        title="Discovery verification",
        purpose="Verify task discovery.",
    )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    provider = FakeImplementationProvider(
        ImplementationResult(
            task_id=task.id,
            summary="Verification prepared.",
            tests=["npm run typecheck"],
            blockers=[
                {
                    "message": (
                        "The discovery API test file contains a TypeScript "
                        "identifier error that must be corrected."
                    ),
                    "kind": "LOCAL_DEFECT",
                    "scope": "WORKSPACE",
                    "fixable_by_agent": True,
                    "requires_human_input": False,
                    "blocking": True,
                }
            ],
        )
    )

    # A defect the agent can fix itself is never a blocker.
    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert execution.result.blockers[0].blocking is False
    assert execution.tests_passed is True


class SequencedImplementationProvider:
    """Return one prepared result per call, in order."""

    def __init__(
        self,
        results: list[ImplementationResult],
    ) -> None:
        self.pending = list(results)
        self.prompts: list[str] = []

    def implement(
        self,
        prompt: str,
    ) -> ImplementationResult:
        self.prompts.append(prompt)

        if not self.pending:
            raise AssertionError(
                "Provider was called more times than expected."
            )

        return self.pending.pop(0)


def _task_repository_task() -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-TASK-REPOSITORY",
        title="Task repository",
        purpose="Implement the task repository.",
    )


def _task_repository_result(
    tests: list[str],
    with_test_file: bool = True,
) -> ImplementationResult:
    files = [
        ImplementationFileChange(
            path="src/modules/tasks/task-repository.ts",
            content="export const taskRepository = {};\n",
        ),
    ]

    if with_test_file:
        files.append(
            ImplementationFileChange(
                path="src/modules/tasks/task-repository.test.ts",
                content="// task repository tests\n",
            )
        )

    return ImplementationResult(
        task_id="TASKFLOW-DEV-TASK-REPOSITORY",
        summary="Repository implemented.",
        files=files,
        tests=tests,
    )


def _write_existing_test_file(
    root: Path,
    relative_path: str,
) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// existing test\n", encoding="utf-8")


def _stub_passing_test_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        lambda **kwargs: CommandExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )


def test_intermediate_task_reprompts_for_task_scoped_test_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task_repository_task()

    targeted = (
        "npm test -- "
        "src/modules/tasks/task-repository.test.ts"
    )

    provider = SequencedImplementationProvider(
        [
            _task_repository_result(
                tests=["npm test"],
            ),
            _task_repository_result(
                tests=[targeted],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "## Required Corrections" not in provider.prompts[0]
    assert "## Required Corrections" in provider.prompts[1]

    assert execution.result.tests == [targeted]
    assert execution.tests_passed

    assert (
        tmp_path
        / "src"
        / "modules"
        / "tasks"
        / "task-repository.ts"
    ).is_file()


def test_rejected_response_is_not_applied_before_the_correction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task_repository_task()

    rejected = _task_repository_result(
        tests=["npm test"],
    )
    rejected.files = [
        ImplementationFileChange(
            path="src/modules/tasks/rejected.ts",
            content="export const rejected = true;\n",
        ),
    ]

    provider = SequencedImplementationProvider(
        [
            rejected,
            _task_repository_result(
                tests=[
                    "npm test -- "
                    "src/modules/tasks/task-repository.test.ts"
                ],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert not (
        tmp_path
        / "src"
        / "modules"
        / "tasks"
        / "rejected.ts"
    ).exists()


def test_test_scope_correction_names_rejected_command_and_test_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task_repository_task()

    provider = SequencedImplementationProvider(
        [
            _task_repository_result(
                tests=["npm test"],
            ),
            _task_repository_result(
                tests=[
                    "npm test -- "
                    "src/modules/tasks/task-repository.test.ts"
                ],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    correction_prompt = provider.prompts[1]

    assert (
        "The previous response was rejected by the Factory runtime "
        "and was not applied."
        in correction_prompt
    )
    assert (
        "Return a corrected response for task "
        "TASKFLOW-DEV-TASK-REPOSITORY."
        in correction_prompt
    )
    assert (
        "Rejected test command: npm test"
        in correction_prompt
    )
    assert (
        "For targeted Node.js tests, use: npm test -- <test-file>."
        in correction_prompt
    )
    assert (
        "Test files produced or modified by this task: "
        "src/modules/tasks/task-repository.test.ts"
        in correction_prompt
    )
    assert (
        "Do not report this correction as a blocker."
        in correction_prompt
    )


def test_test_scope_correction_requests_a_test_file_when_none_was_returned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task_repository_task()

    provider = SequencedImplementationProvider(
        [
            _task_repository_result(
                tests=["npm test"],
                with_test_file=False,
            ),
            _task_repository_result(
                tests=[
                    "npm test -- "
                    "src/modules/tasks/task-repository.test.ts"
                ],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert (
        "This task returned no test file, so add the automated test "
        "it requires and scope the replacement command to that test file."
        in provider.prompts[1]
    )


def test_intermediate_task_rejects_full_project_suite_after_correction(
    tmp_path: Path,
) -> None:
    task = _task_repository_task()

    provider = SequencedImplementationProvider(
        [
            _task_repository_result(
                tests=["npm test"],
            ),
            _task_repository_result(
                tests=["npm run test"],
            ),
        ]
    )

    with pytest.raises(
        ValueError,
        match="Full-project test suite is not allowed",
    ):
        run_implementation_task(
            project_root=tmp_path,
            task=task,
            context={},
            provider=provider,
        )

    assert len(provider.prompts) == 2
    assert provider.pending == []

    assert not (
        tmp_path
        / "src"
        / "modules"
        / "tasks"
        / "task-repository.ts"
    ).exists()


def test_verification_task_keeps_full_project_suite_without_reprompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-FULL-VERIFICATION",
        title="Full verification",
        purpose="Run the full project verification suite.",
    )

    provider = SequencedImplementationProvider(
        [
            ImplementationResult(
                task_id=task.id,
                summary="Verified.",
                tests=["npm test"],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 1
    assert "## Required Corrections" not in provider.prompts[0]
    assert execution.result.tests == ["npm test"]
    assert execution.tests_passed


def _classify(
    task_id: str,
    title: str,
    purpose: str = "Implement the unit.",
) -> bool:
    from ai_factory.implementation_runtime import (
        _is_verification_task,
    )

    return _is_verification_task(
        ImplementationTask(
            agent_name="developer",
            id=task_id,
            title=title,
            purpose=purpose,
        )
    )


def test_narrow_test_units_are_not_verification_tasks() -> None:
    assert not _classify(
        "TASKFLOW-DEV-TASK-REPOSITORY-TESTS",
        "Repository tests",
    )
    assert not _classify(
        "TASKFLOW-DEV-DISCOVERY-API-TESTS",
        "Discovery API tests",
    )
    assert not _classify(
        "TASKFLOW-DEV-AUTHENTICATION-TESTS",
        "Authentication tests",
    )
    assert not _classify(
        "TASKFLOW-DEV-UI-TESTS",
        "UI tests",
    )
    assert not _classify(
        "TASKFLOW-DEV-DISCOVERY-TEST-REPAIR",
        "Discovery test repair",
    )
    assert not _classify(
        "TASKFLOW-DEV-DISCOVERY-VERIFICATION",
        "Discovery verification",
    )


def test_project_wide_units_are_verification_tasks() -> None:
    assert _classify(
        "TASKFLOW-DEV-FULL-VERIFICATION",
        "Full verification",
    )
    assert _classify(
        "TASKFLOW-DEV-FINAL-VERIFICATION",
        "Final verification",
    )
    assert _classify(
        "TASKFLOW-DEV-FULL-MVP-VERIFICATION",
        "Full MVP verification",
    )
    assert _classify(
        "TASKFLOW-DEV-E2E-TESTS",
        "End-to-end tests",
    )
    assert _classify(
        "TASKFLOW-DEV-FULL-TEST-SUITE",
        "Full test suite",
    )


def test_verification_requires_both_scope_and_activity() -> None:
    assert not _classify(
        "TASKFLOW-DEV-FULL-TASK-FORM",
        "Full task form",
    )
    assert not _classify(
        "TASKFLOW-DEV-TASK-VERIFY-OWNERSHIP",
        "Verify task ownership",
    )


def test_purpose_prose_does_not_promote_a_unit_to_verification() -> None:
    assert not _classify(
        "TASKFLOW-DEV-TASK-REPOSITORY",
        "Task repository",
        purpose=(
            "Implement the task repository and verify it with integration "
            "tests, checking for regressions across the full project."
        ),
    )


def test_narrow_test_unit_is_reprompted_for_task_scoped_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-DISCOVERY-API-TESTS",
        title="Discovery API tests",
        purpose="Add the discovery API tests.",
    )

    targeted = (
        "npm test -- "
        "src/app/api/v1/tasks/discovery-api.test.ts"
    )

    provider = SequencedImplementationProvider(
        [
            ImplementationResult(
                task_id=task.id,
                summary="Discovery API tests added.",
                files=[
                    ImplementationFileChange(
                        path=(
                            "src/app/api/v1/tasks/"
                            "discovery-api.test.ts"
                        ),
                        content="// discovery api tests\n",
                    ),
                ],
                tests=["npm test"],
            ),
            ImplementationResult(
                task_id=task.id,
                summary="Discovery API tests added.",
                files=[
                    ImplementationFileChange(
                        path=(
                            "src/app/api/v1/tasks/"
                            "discovery-api.test.ts"
                        ),
                        content="// discovery api tests\n",
                    ),
                ],
                tests=[targeted],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "## Required Corrections" in provider.prompts[1]
    assert execution.result.tests == [targeted]


def test_narrow_test_unit_captures_a_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="TASKFLOW-DEV-DISCOVERY-API-TESTS",
        title="Discovery API tests",
        purpose="Add the discovery API tests.",
    )

    targeted = (
        "npm test -- "
        "src/app/api/v1/tasks/discovery-api.test.ts"
    )

    # The declared target has to exist: a unit may only validate itself
    # with a test that is present or that it writes.
    _write_existing_test_file(
        tmp_path,
        "src/app/api/v1/tasks/discovery-api.test.ts",
    )

    provider = SequencedImplementationProvider(
        [
            ImplementationResult(
                task_id=task.id,
                summary="Discovery API tests added.",
                tests=[targeted],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={},
        provider=provider,
    )

    assert [
        item.command
        for item in execution.baseline_test_results
    ] == [targeted]


def _typecheck_failure(
    stdout: str,
) -> CommandExecutionResult:
    return CommandExecutionResult(
        command="npm run typecheck",
        returncode=1,
        stdout=stdout,
        stderr="",
    )


def test_preexisting_failure_in_project_named_directory_is_not_blamed() -> None:
    from ai_factory.implementation_runtime import (
        ImplementationExecution,
    )

    unrelated = (
        "src/shoplite/ui/button.tsx(12,3): error TS2322"
    )

    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="SHOPLITE-DEV-CART-REPOSITORY",
            summary="Cart repository implemented.",
            tests=["npm run typecheck"],
        ),
        task_id="SHOPLITE-DEV-CART-REPOSITORY",
        project_identity=("shop", "lite"),
        baseline_test_results=[
            _typecheck_failure(unrelated),
        ],
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "passed": False,
                "stdout": unrelated,
                "stderr": "",
            },
        ],
        test_results=[
            _typecheck_failure(unrelated),
        ],
    )

    assert execution.tests_passed


def test_regression_on_a_task_related_path_is_still_blamed() -> None:
    from ai_factory.implementation_runtime import (
        ImplementationExecution,
    )

    related = (
        "src/modules/cart/cart-repository.ts(31,27): error TS2339"
    )

    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="SHOPLITE-DEV-CART-REPOSITORY",
            summary="Cart repository implemented.",
            tests=["npm run typecheck"],
        ),
        task_id="SHOPLITE-DEV-CART-REPOSITORY",
        project_identity=("shop", "lite"),
        baseline_test_results=[
            _typecheck_failure(related),
        ],
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "passed": False,
                "stdout": related,
                "stderr": "",
            },
        ],
        test_results=[
            _typecheck_failure(related),
        ],
    )

    assert not execution.tests_passed


def test_taskflow_regression_attribution_is_unchanged() -> None:
    from ai_factory.implementation_runtime import (
        ImplementationExecution,
    )

    related = (
        "src/modules/tasks/task-repository.ts(31,27): error TS2339"
    )

    execution = ImplementationExecution(
        result=ImplementationResult(
            task_id="TASKFLOW-DEV-TASK-REPOSITORY",
            summary="Task repository implemented.",
        ),
        task_id="TASKFLOW-DEV-TASK-REPOSITORY",
        project_identity=("task", "flow"),
        baseline_test_results=[
            _typecheck_failure(related),
        ],
        retry_test_results=[
            {
                "command": "npm run typecheck",
                "passed": False,
                "stdout": related,
                "stderr": "",
            },
        ],
        test_results=[
            _typecheck_failure(related),
        ],
    )

    assert not execution.tests_passed


def test_run_implementation_task_propagates_project_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = ImplementationTask(
        agent_name="developer",
        id="SHOPLITE-DEV-CART-REPOSITORY",
        title="Cart repository",
        purpose="Implement the cart repository.",
    )

    _write_existing_test_file(
        tmp_path,
        "src/modules/cart/cart-repository.test.ts",
    )

    provider = SequencedImplementationProvider(
        [
            ImplementationResult(
                task_id=task.id,
                summary="Cart repository implemented.",
                tests=[
                    "npm test -- "
                    "src/modules/cart/cart-repository.test.ts"
                ],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=task,
        context={
            "state": {
                "project": {
                    "id": "shop-lite",
                    "name": "ShopLite",
                }
            }
        },
        provider=provider,
    )

    assert execution.project_identity == (
        "shop",
        "lite",
    )


def _cli_task() -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id="todo-cli",
        title="CLI entry point",
        purpose="Implement the command-line entry point.",
    )


def _cli_result(
    tests: list[str],
    with_test_file: bool = False,
) -> ImplementationResult:
    files = [
        ImplementationFileChange(
            path="todo/__main__.py",
            content="print('todo')\n",
        ),
    ]

    if with_test_file:
        files.append(
            ImplementationFileChange(
                path="tests/test_cli.py",
                content="def test_cli():\n    assert True\n",
            )
        )

    return ImplementationResult(
        task_id="todo-cli",
        summary="CLI implemented.",
        files=files,
        tests=tests,
    )


def test_task_referencing_a_test_file_it_does_not_write_is_corrected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SequencedImplementationProvider(
        [
            _cli_result(
                tests=["python -m pytest tests/test_cli_entry_point.py"],
            ),
            _cli_result(
                tests=["python -m pytest tests/test_cli.py"],
                with_test_file=True,
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_cli_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "## Required Corrections" in provider.prompts[1]
    assert (
        "tests/test_cli_entry_point.py"
        in provider.prompts[1]
    )
    assert execution.execution_succeeded
    assert (tmp_path / "tests" / "test_cli.py").is_file()


def test_task_writing_its_own_test_file_is_not_corrected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SequencedImplementationProvider(
        [
            _cli_result(
                tests=["python -m pytest ./tests/test_cli.py::test_cli"],
                with_test_file=True,
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_cli_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 1
    assert execution.execution_succeeded


def test_task_validating_with_an_existing_test_file_is_not_corrected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = tmp_path / "tests" / "test_service.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    provider = SequencedImplementationProvider(
        [
            _cli_result(
                tests=["python -m pytest tests/test_service.py"],
            ),
        ]
    )

    _stub_passing_test_command(monkeypatch)

    run_implementation_task(
        project_root=tmp_path,
        task=_cli_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 1


def test_missing_test_target_on_last_attempt_still_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = _cli_result(
        tests=["python -m pytest tests/test_cli_entry_point.py"],
    )

    provider = SequencedImplementationProvider(
        [missing, missing],
    )

    _stub_passing_test_command(monkeypatch)

    execution = run_implementation_task(
        project_root=tmp_path,
        task=_cli_task(),
        context={},
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert execution.invalid_validation_targets == [
        "tests/test_cli_entry_point.py",
    ]
    assert not execution.execution_succeeded
    assert not (tmp_path / "todo" / "__main__.py").exists()
