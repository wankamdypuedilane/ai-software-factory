"""The retry context must stay repairable without copying a workspace.

Files an agent authored are the material a retry needs. Artifacts produced by
setup commands - lockfiles, generated clients, build outputs - are recorded by
name only: reinjecting them verbatim is what blew the LinkVault retry prompt
past 200k characters.
"""

from pathlib import Path

import pytest

from ai_factory.implementation_contract import (
    ImplementationScope,
    ImplementationTaskKind,
    VerificationPolicy,
)
from ai_factory.implementation_prompt import (
    MAX_FAILED_ATTEMPT_FILE_CHARS,
    MAX_FAILED_ATTEMPT_TOTAL_CHARS,
    MAX_RELEVANT_ARTIFACTS_TOTAL_CHARS,
    MAX_WORKSPACE_FILES_TOTAL_CHARS,
    build_implementation_prompt,
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
    load_failed_transaction_generated_paths,
    load_failed_transaction_snapshot,
    save_failed_transaction_snapshot,
)


TASK_ID = "ACME-DEV-FOUNDATION"


def _task() -> ImplementationTask:
    return ImplementationTask(
        agent_name="developer",
        id=TASK_ID,
        title="Foundation",
        purpose="Implement the foundation.",
        kind=ImplementationTaskKind.IMPLEMENTATION,
        scope=ImplementationScope.TASK,
        verification=VerificationPolicy(
            allow_full_suite=False,
            baseline_required=True,
        ),
    )


def _empty_context() -> dict:
    return {
        "project": {},
        "state": {},
        "artifacts": {},
    }


# --------------------------------------------------------------------------
# Snapshot separation
# --------------------------------------------------------------------------


def test_snapshot_separates_authored_files_from_generated_artifacts(
    tmp_path: Path,
) -> None:
    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id=TASK_ID,
        files={
            "src/app.ts": "export const app = 1;\n",
        },
        generated_paths=[
            "package-lock.json",
            "node_modules/.prisma/client/index.js",
        ],
    )

    assert load_failed_transaction_snapshot(
        tmp_path,
        TASK_ID,
    ) == {
        "src/app.ts": "export const app = 1;\n",
    }

    assert load_failed_transaction_generated_paths(
        tmp_path,
        TASK_ID,
    ) == [
        "node_modules/.prisma/client/index.js",
        "package-lock.json",
    ]


def test_generated_artifact_content_is_never_persisted(
    tmp_path: Path,
) -> None:
    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id=TASK_ID,
        files={
            "src/app.ts": "export const app = 1;\n",
        },
        generated_paths=[
            "package-lock.json",
        ],
    )

    stored = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".factory" / "failed-transactions"
        ).rglob("*")
        if path.is_file()
    ]

    assert not any(
        "lockfileVersion" in content
        for content in stored
    )


def test_runtime_records_setup_artifacts_by_name_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "src").mkdir()

    lockfile_content = '{"lockfileVersion": 3, "packages": {}}' + "x" * 50_000

    def generate(**kwargs):
        root = kwargs["project_root"]
        (root / "package-lock.json").write_text(
            lockfile_content,
            encoding="utf-8",
        )

        return SetupExecutionResult(
            command=kwargs["command"],
            returncode=0,
            stdout="",
            stderr="",
        )

    codes = [0, 1]

    def failing_test(**kwargs):
        returncode = codes.pop(0) if codes else 1

        return CommandExecutionResult(
            command=kwargs["command"],
            returncode=returncode,
            stdout="",
            stderr="boom" if returncode else "",
        )

    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_setup_command",
        generate,
    )
    monkeypatch.setattr(
        "ai_factory.implementation_runtime.run_test_command",
        failing_test,
    )

    class Provider:
        def implement(self, prompt: str) -> ImplementationResult:
            return ImplementationResult(
                task_id=TASK_ID,
                summary="Foundation implemented.",
                files=[
                    ImplementationFileChange(
                        path="src/app.ts",
                        content="export const app = 1;\n",
                    ),
                ],
                setup_commands=["npm install --ignore-scripts"],
                tests=["npm test -- tests/app.test.ts"],
            )

    run_implementation_task(
        project_root=tmp_path,
        task=_task(),
        context={},
        provider=Provider(),
    )

    assert load_failed_transaction_snapshot(
        tmp_path,
        TASK_ID,
    ) == {
        "src/app.ts": "export const app = 1;\n",
    }

    assert "package-lock.json" in (
        load_failed_transaction_generated_paths(
            tmp_path,
            TASK_ID,
        )
    )


# --------------------------------------------------------------------------
# Prompt budget
# --------------------------------------------------------------------------


def test_generated_artifacts_are_listed_without_content() -> None:
    prompt = build_implementation_prompt(
        task=_task(),
        context=_empty_context(),
        retry_test_results=[{"command": "npm test"}],
        failed_attempt_files={
            "src/app.ts": "export const app = 1;\n",
        },
        failed_attempt_generated_paths=[
            "package-lock.json",
        ],
    )

    assert "## Previous Failed Attempt" in prompt
    assert "export const app = 1;" in prompt
    assert "package-lock.json" in prompt
    assert "Generated by setup commands" in prompt


def test_failed_attempt_file_is_capped() -> None:
    oversized = "A" * (MAX_FAILED_ATTEMPT_FILE_CHARS * 3)

    prompt = build_implementation_prompt(
        task=_task(),
        context=_empty_context(),
        failed_attempt_files={
            "src/big.ts": oversized,
        },
    )

    assert "characters omitted" in prompt
    assert len(prompt) < len(oversized)


def test_failed_attempt_section_has_a_total_budget() -> None:
    files = {
        f"src/module{index}.ts": "B" * MAX_FAILED_ATTEMPT_FILE_CHARS
        for index in range(40)
    }

    prompt = build_implementation_prompt(
        task=_task(),
        context=_empty_context(),
        failed_attempt_files=files,
    )

    section = prompt[prompt.index("## Previous Failed Attempt"):]

    assert len(section) < MAX_FAILED_ATTEMPT_TOTAL_CHARS * 2
    assert "files omitted" in section


def test_relevant_artifacts_have_a_total_budget() -> None:
    context = _empty_context()
    context["artifacts"] = {
        f"knowledge/doc{index}.md": "C" * 6000
        for index in range(30)
    }

    prompt = build_implementation_prompt(
        task=_task(),
        context=context,
    )

    assert len(prompt) < MAX_RELEVANT_ARTIFACTS_TOTAL_CHARS * 3


def test_workspace_files_have_a_total_budget() -> None:
    prompt = build_implementation_prompt(
        task=_task(),
        context=_empty_context(),
        workspace_files={
            f"src/file{index}.ts": "D" * 6000
            for index in range(30)
        },
    )

    assert len(prompt) < MAX_WORKSPACE_FILES_TOTAL_CHARS * 3
