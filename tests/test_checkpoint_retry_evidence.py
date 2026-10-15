"""Retry evidence must survive the checkpoint that references it.

Round 12 replayed LinkVault from a checkpoint whose state still named
`failed_task_id = LV-DEV-004` and listed the files that attempt authored,
while the evidence describing it had been destroyed three separate ways: the
checkpoint never captured `.factory/failed-transactions`, the restore never
wrote it back, and the restore purged whatever was on disk. The retry prompt
lost its entire `## Previous Failed Attempt` section - 3367 characters - and
said nothing about the loss.

A checkpoint's state and a checkpoint's retry evidence must describe the same
workflow moment. Evidence produced after the checkpoint must never survive
into a replay of it.
"""

import json
from pathlib import Path

import pytest

from ai_factory.factory_checkpoint import (
    CHECKPOINT_FILES_DIRECTORY,
    IncompatibleCheckpointError,
    create_checkpoint,
    restore_checkpoint,
)
from ai_factory.implementation_prompt import (
    MAX_FAILED_ATTEMPT_TOTAL_CHARS,
    build_implementation_prompt,
)
from ai_factory.implementation_request import ImplementationTask
from ai_factory.implementation_result import ImplementationResult
from ai_factory.implementation_runtime import run_implementation_task
from ai_factory.retry_evidence import (
    RETRY_EVIDENCE_DIRECTORY,
    bound_authored_files,
    collect_retry_evidence,
    resolve_failed_attempt_evidence,
    state_failed_attempt_paths,
)
from ai_factory.state import load_state, save_state
from ai_factory.workspace_transaction import (
    load_failed_transaction_generated_paths,
    load_failed_transaction_snapshot,
    save_failed_transaction_snapshot,
)


PASSWORD_SOURCE = (
    "import argon2 from 'argon2';\n"
    "export const hashPassword = (value: string) =>\n"
    "  argon2.hash(value, { type: argon2.argon2id });\n"
)

PASSWORD_TEST = (
    "import { describe, it, expect } from 'vitest';\n"
    "import { hashPassword } from './password';\n"
    "describe('password', () => {\n"
    "  it('hashes', async () => {\n"
    "    expect(await hashPassword('x')).toContain('argon2id');\n"
    "  });\n"
    "});\n"
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _state(
    failed_task_id: str = "LV-DEV-004",
    files: list[str] | None = None,
) -> dict:
    return {
        "project": {
            "id": "linkvault",
            "name": "LinkVault",
            "phase": "implementation",
        },
        "agents": {
            "developer": {
                "status": "FAILED",
                "last_result": {
                    "summary": "Password hashing failed.",
                    "failed_task_id": failed_task_id,
                    "failure_signature": (
                        "test_failed|npm test -- src/auth/password.test.ts"
                    ),
                    "replan_count": 2,
                    "repeated_failures": 0,
                    "implemented_files": ["package.json"],
                    "implementation_requests": [
                        {
                            "id": failed_task_id,
                            "title": "Implement password hashing",
                            "purpose": "Hash passwords with Argon2id.",
                        }
                    ],
                    "implementation_results": [
                        {
                            "task_id": failed_task_id,
                            "summary": "Password hashing implemented.",
                            "files": files
                            if files is not None
                            else [
                                "src/auth/password.ts",
                                "src/auth/password.test.ts",
                            ],
                            "tests": [
                                "npm test -- src/auth/password.test.ts"
                            ],
                            "blockers": [],
                        }
                    ],
                    "test_results": [
                        {
                            "command": (
                                "npm test -- src/auth/password.test.ts"
                            ),
                            "passed": False,
                            "returncode": 1,
                            "stdout": "",
                            "stderr": "No test files found",
                        }
                    ],
                }
            }
        },
    }


def _project(
    root: Path,
    failed_task_id: str = "LV-DEV-004",
    with_snapshot: bool = True,
    files: list[str] | None = None,
) -> None:
    (root / ".factory").mkdir(parents=True, exist_ok=True)

    save_state(
        root / ".factory" / "state.yaml",
        _state(failed_task_id, files),
    )

    save_state(
        root / ".factory" / "project.yaml",
        {"schema_version": 1, "project": {"name": "LinkVault"}},
    )

    (root / "package.json").write_text(
        json.dumps({"name": "linkvault", "dependencies": {}}),
        encoding="utf-8",
    )

    if with_snapshot:
        save_failed_transaction_snapshot(
            project_root=root,
            task_id=failed_task_id,
            files={
                "src/auth/password.ts": PASSWORD_SOURCE,
                "src/auth/password.test.ts": PASSWORD_TEST,
            },
            generated_paths=["package-lock.json"],
        )


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------


def test_failed_attempt_evidence_exists_before_the_checkpoint(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    snapshot = load_failed_transaction_snapshot(tmp_path, "LV-DEV-004")

    assert sorted(snapshot) == [
        "src/auth/password.test.ts",
        "src/auth/password.ts",
    ]
    assert load_failed_transaction_generated_paths(
        tmp_path, "LV-DEV-004"
    ) == ["package-lock.json"]


def test_checkpoint_captures_evidence_for_the_failed_task(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    evidence_root = (
        tmp_path
        / ".factory"
        / "checkpoints"
        / "milestone"
        / RETRY_EVIDENCE_DIRECTORY
        / "LV-DEV-004"
    )

    assert (evidence_root / "files" / "src/auth/password.ts").is_file()
    assert (
        evidence_root / "files" / "src/auth/password.test.ts"
    ).is_file()
    assert "package-lock.json" in (
        evidence_root / "generated-artifacts.txt"
    ).read_text(encoding="utf-8")


def test_checkpoint_does_not_capture_an_unrelated_failed_transaction(
    tmp_path: Path,
) -> None:
    """Only the attempt the state references is evidence for this moment."""

    _project(tmp_path)

    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id="LV-DEV-999",
        files={"src/other/unrelated.ts": "export const other = 1;\n"},
        generated_paths=[],
    )

    create_checkpoint(tmp_path, "milestone")

    store = (
        tmp_path
        / ".factory"
        / "checkpoints"
        / "milestone"
        / RETRY_EVIDENCE_DIRECTORY
    )

    assert sorted(item.name for item in store.iterdir()) == ["LV-DEV-004"]


def test_checkpoint_files_still_exclude_the_live_transaction_directory(
    tmp_path: Path,
) -> None:
    """Evidence is owned by the checkpoint, not smuggled in as a file."""

    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    files_root = (
        tmp_path
        / ".factory"
        / "checkpoints"
        / "milestone"
        / CHECKPOINT_FILES_DIRECTORY
    )

    assert not (files_root / ".factory" / "failed-transactions").exists()


# --------------------------------------------------------------------------
# Restore
# --------------------------------------------------------------------------


def test_restore_purges_evidence_created_after_the_checkpoint(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    # A later run fails differently and leaves its own evidence behind.
    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id="LV-DEV-777",
        files={"src/later/run.ts": "export const later = 1;\n"},
        generated_paths=[],
    )

    restore_checkpoint(tmp_path, "milestone")

    assert load_failed_transaction_snapshot(tmp_path, "LV-DEV-777") == {}


def test_restore_writes_back_the_evidence_the_checkpoint_owns(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    # The live evidence is destroyed between checkpoint and replay.
    import shutil

    shutil.rmtree(tmp_path / ".factory" / "failed-transactions")

    restore_checkpoint(tmp_path, "milestone")

    snapshot = load_failed_transaction_snapshot(tmp_path, "LV-DEV-004")

    assert snapshot["src/auth/password.ts"] == PASSWORD_SOURCE
    assert snapshot["src/auth/password.test.ts"] == PASSWORD_TEST
    assert load_failed_transaction_generated_paths(
        tmp_path, "LV-DEV-004"
    ) == ["package-lock.json"]


def test_restoring_a_checkpoint_cannot_inherit_later_evidence(
    tmp_path: Path,
) -> None:
    """Checkpoint A must never gain the evidence of a later run B."""

    _project(tmp_path, with_snapshot=False)

    create_checkpoint(tmp_path, "milestone-a")

    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id="LV-DEV-004",
        files={"src/auth/password.ts": "// written by the later run B\n"},
        generated_paths=["package-lock.json"],
    )

    restore_checkpoint(tmp_path, "milestone-a")

    assert load_failed_transaction_snapshot(tmp_path, "LV-DEV-004") == {}


def test_the_workspace_never_regains_the_failed_authored_files(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")
    restore_checkpoint(tmp_path, "milestone")

    assert not (tmp_path / "src" / "auth" / "password.ts").exists()
    assert not (tmp_path / "src" / "auth" / "password.test.ts").exists()


def test_a_failed_restore_leaves_workspace_state_and_evidence_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    (tmp_path / "package.json").write_text(
        json.dumps({"name": "linkvault", "dependencies": {"argon2": "1"}}),
        encoding="utf-8",
    )

    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id="LV-DEV-555",
        files={"src/live/current.ts": "export const live = 1;\n"},
        generated_paths=[],
    )

    package_before = (tmp_path / "package.json").read_bytes()
    state_before = load_state(tmp_path / ".factory" / "state.yaml")

    import ai_factory.factory_checkpoint as checkpoint_module

    def explode(*args, **kwargs):
        raise OSError("disk failure during restore")

    monkeypatch.setattr(
        checkpoint_module,
        "restore_retry_evidence",
        explode,
    )

    with pytest.raises(OSError):
        restore_checkpoint(tmp_path, "milestone")

    assert (tmp_path / "package.json").read_bytes() == package_before
    assert load_state(tmp_path / ".factory" / "state.yaml") == state_before

    assert load_failed_transaction_snapshot(tmp_path, "LV-DEV-555") == {
        "src/live/current.ts": "export const live = 1;\n"
    }


def test_a_checkpoint_from_another_project_is_still_rejected(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    state = load_state(tmp_path / ".factory" / "state.yaml")
    state["project"]["id"] = "another-project"
    save_state(tmp_path / ".factory" / "state.yaml", state)

    with pytest.raises(IncompatibleCheckpointError, match="different project"):
        restore_checkpoint(tmp_path, "milestone")


def test_the_engine_compatibility_guard_is_unchanged(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")

    metadata_path = (
        tmp_path
        / ".factory"
        / "checkpoints"
        / "milestone"
        / "checkpoint.yaml"
    )

    metadata = load_state(metadata_path)
    metadata["engine_fingerprint"] = "0" * 64
    save_state(metadata_path, metadata)

    with pytest.raises(IncompatibleCheckpointError, match="engine build"):
        restore_checkpoint(tmp_path, "milestone")

    restore_checkpoint(tmp_path, "milestone", allow_engine_change=True)


# --------------------------------------------------------------------------
# Storage budget
# --------------------------------------------------------------------------


def test_stored_contents_obey_the_prompt_budget() -> None:
    files = {
        f"src/file{index}.ts": "x" * 9000
        for index in range(6)
    }

    bounded, truncated = bound_authored_files(files)

    assert truncated is True
    assert sum(len(value) for value in bounded.values()) <= (
        MAX_FAILED_ATTEMPT_TOTAL_CHARS
    )


def test_oversized_evidence_is_truncated_deterministically() -> None:
    files = {
        f"src/file{index}.ts": "x" * 9000
        for index in range(6)
    }

    first, _ = bound_authored_files(files)
    second, _ = bound_authored_files(dict(reversed(list(files.items()))))

    assert first == second


def test_evidence_within_budget_is_stored_verbatim() -> None:
    files = {"src/auth/password.ts": PASSWORD_SOURCE}

    bounded, truncated = bound_authored_files(files)

    assert bounded == files
    assert truncated is False


def test_capture_writes_only_what_the_prompt_could_consume(
    tmp_path: Path,
) -> None:
    _project(tmp_path, with_snapshot=False)

    save_failed_transaction_snapshot(
        project_root=tmp_path,
        task_id="LV-DEV-004",
        files={"src/huge.ts": "y" * 80000},
        generated_paths=[],
    )

    create_checkpoint(tmp_path, "milestone")

    stored = (
        tmp_path
        / ".factory"
        / "checkpoints"
        / "milestone"
        / RETRY_EVIDENCE_DIRECTORY
        / "LV-DEV-004"
        / "files"
        / "src"
        / "huge.ts"
    )

    assert len(stored.read_text(encoding="utf-8")) <= (
        MAX_FAILED_ATTEMPT_TOTAL_CHARS
    )


# --------------------------------------------------------------------------
# Fallback D - structural evidence with no durable contents
# --------------------------------------------------------------------------


def test_fallback_reads_paths_from_implementation_results(
    tmp_path: Path,
) -> None:
    state = _state()

    assert state_failed_attempt_paths(state, "LV-DEV-004") == [
        "src/auth/password.ts",
        "src/auth/password.test.ts",
    ]


def test_fallback_does_not_require_the_files_to_exist_on_disk(
    tmp_path: Path,
) -> None:
    _project(tmp_path, with_snapshot=False)

    state = load_state(tmp_path / ".factory" / "state.yaml")

    evidence = resolve_failed_attempt_evidence(
        project_root=tmp_path,
        state=state,
        task_id="LV-DEV-004",
    )

    assert evidence.contents_available is False
    assert evidence.authored_files == {}
    assert evidence.paths == [
        "src/auth/password.ts",
        "src/auth/password.test.ts",
    ]
    assert not (tmp_path / "src" / "auth" / "password.ts").exists()


def test_a_legacy_checkpoint_without_durable_evidence_falls_back(
    tmp_path: Path,
) -> None:
    """A checkpoint taken before this patch keeps working."""

    _project(tmp_path)

    create_checkpoint(tmp_path, "legacy")

    # Simulate a checkpoint created by the previous engine: no evidence.
    import shutil

    shutil.rmtree(
        tmp_path
        / ".factory"
        / "checkpoints"
        / "legacy"
        / RETRY_EVIDENCE_DIRECTORY
    )

    restore_checkpoint(tmp_path, "legacy")

    state = load_state(tmp_path / ".factory" / "state.yaml")

    evidence = resolve_failed_attempt_evidence(
        project_root=tmp_path,
        state=state,
        task_id="LV-DEV-004",
    )

    assert evidence.contents_available is False
    assert evidence.paths == [
        "src/auth/password.ts",
        "src/auth/password.test.ts",
    ]


def test_durable_evidence_is_preferred_over_the_fallback(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "milestone")
    restore_checkpoint(tmp_path, "milestone")

    state = load_state(tmp_path / ".factory" / "state.yaml")

    evidence = resolve_failed_attempt_evidence(
        project_root=tmp_path,
        state=state,
        task_id="LV-DEV-004",
    )

    assert evidence.contents_available is True
    assert evidence.authored_files["src/auth/password.ts"] == PASSWORD_SOURCE


def test_no_failed_task_yields_no_evidence(tmp_path: Path) -> None:
    _project(tmp_path, with_snapshot=False)

    state = load_state(tmp_path / ".factory" / "state.yaml")
    state["agents"]["developer"]["last_result"]["failed_task_id"] = ""
    save_state(tmp_path / ".factory" / "state.yaml", state)

    assert collect_retry_evidence(tmp_path, state) is None


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


def test_the_prompt_states_paths_were_rolled_back_without_contents() -> None:
    prompt = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="LV-DEV-004",
            title="Implement password hashing",
            purpose="Hash passwords with Argon2id.",
        ),
        context={},
        retry_test_results=[
            {
                "command": "npm test -- src/auth/password.test.ts",
                "returncode": 1,
                "stdout": "",
                "stderr": "No test files found",
            }
        ],
        workspace_files={"package.json": "{}"},
        failed_attempt_paths=[
            "src/auth/password.ts",
            "src/auth/password.test.ts",
        ],
    )

    assert "## Previous Failed Attempt" in prompt
    assert "rolled back" in prompt
    assert "NOT present in the workspace" in prompt
    assert "src/auth/password.test.ts" in prompt
    assert "contents" in prompt.lower()


def test_the_prompt_marks_that_only_structural_evidence_was_available(
) -> None:
    """Missing durable evidence must stop being silent."""

    with_contents = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="LV-DEV-004",
            title="Implement password hashing",
            purpose="Hash passwords.",
        ),
        context={},
        retry_test_results=[{"command": "npm test", "returncode": 1}],
        failed_attempt_files={"src/auth/password.ts": PASSWORD_SOURCE},
    )

    without_contents = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="LV-DEV-004",
            title="Implement password hashing",
            purpose="Hash passwords.",
        ),
        context={},
        retry_test_results=[{"command": "npm test", "returncode": 1}],
        failed_attempt_paths=["src/auth/password.ts"],
    )

    marker = "only the file paths of the previous attempt were recovered"

    assert marker in without_contents
    assert marker not in with_contents


# --------------------------------------------------------------------------
# Integration: the retry prompt across a restore
# --------------------------------------------------------------------------


class _Capturing:
    def __init__(self) -> None:
        self.prompt = ""

    def implement(self, prompt: str) -> ImplementationResult:
        self.prompt = prompt
        raise _Captured


class _Captured(Exception):
    pass


def _retry_prompt(root: Path) -> str:
    state = load_state(root / ".factory" / "state.yaml")
    provider = _Capturing()

    try:
        run_implementation_task(
            project_root=root,
            task=ImplementationTask(
                agent_name="developer",
                id="LV-DEV-004",
                title="Implement password hashing",
                purpose="Hash passwords with Argon2id.",
            ),
            context={"state": state},
            provider=provider,
            retry_test_results=[
                {
                    "command": "npm test -- src/auth/password.test.ts",
                    "passed": False,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "No test files found",
                }
            ],
        )
    except _Captured:
        pass

    return provider.prompt


def _section_size(prompt: str, heading: str) -> int:
    start = prompt.find("\n" + heading)

    if start < 0:
        return 0

    end = len(prompt)

    for candidate in (
        "## Previous Test Failures",
        "## Implementation Instructions",
    ):
        position = prompt.find("\n" + candidate, start + 1)

        if position > 0:
            end = min(end, position)

    return end - start


def test_previous_failed_attempt_survives_a_checkpoint_restore(
    tmp_path: Path,
) -> None:
    """The Round-12 regression, end to end."""

    _project(tmp_path)

    before = _retry_prompt(tmp_path)
    before_size = _section_size(before, "## Previous Failed Attempt")

    assert before_size > 0
    assert PASSWORD_SOURCE.strip() in before

    create_checkpoint(tmp_path, "developer-progress")
    restore_checkpoint(tmp_path, "developer-progress")

    after = _retry_prompt(tmp_path)
    after_size = _section_size(after, "## Previous Failed Attempt")

    assert after_size > 0
    assert PASSWORD_SOURCE.strip() in after
    assert "src/auth/password.test.ts" in after
    assert "package-lock.json" in after
    assert "rolled back" in after
    assert "NOT present in the workspace" in after

    # Current workspace and previous attempt stay distinguishable.
    assert "## Current Workspace Files" in after
    assert not (tmp_path / "src" / "auth" / "password.ts").exists()


def test_a_legacy_replay_still_explains_the_previous_attempt(
    tmp_path: Path,
) -> None:
    _project(tmp_path)

    create_checkpoint(tmp_path, "legacy")

    import shutil

    shutil.rmtree(
        tmp_path
        / ".factory"
        / "checkpoints"
        / "legacy"
        / RETRY_EVIDENCE_DIRECTORY
    )

    restore_checkpoint(tmp_path, "legacy")

    prompt = _retry_prompt(tmp_path)

    assert _section_size(prompt, "## Previous Failed Attempt") > 0
    assert "src/auth/password.test.ts" in prompt
    assert "rolled back" in prompt
    assert (
        "only the file paths of the previous attempt were recovered"
        in prompt
    )
