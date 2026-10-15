"""Durable, bounded retry evidence owned by a checkpoint.

A failed transaction snapshot is runtime scratch data: it explains the
attempt that just failed, and it belongs to the run that produced it. Retry
evidence is the far smaller thing a replay needs - which files the failed
attempt authored, what they contained, what its setup commands generated -
so that the next attempt can reason about the previous one.

Round 12 proved the two were conflated. A checkpoint kept a state naming
`failed_task_id` while three separate mechanisms guaranteed the evidence
describing it would be gone: the transaction directory was excluded from the
managed file set, so it was neither captured nor restored, and the restore
purged whatever was on disk. The replay lost its whole `## Previous Failed
Attempt` section and said nothing about it.

Evidence is therefore captured under the checkpoint that references it, is
bounded by what a prompt could ever consume, and is written back only after
the stale live evidence of later runs has been purged.
"""

from dataclasses import dataclass, field
import shutil
from pathlib import Path
from typing import Any

from ai_factory.implementation_prompt import (
    MAX_FAILED_ATTEMPT_FILE_CHARS,
    MAX_FAILED_ATTEMPT_TOTAL_CHARS,
)
from ai_factory.workspace_transaction import (
    FAILED_TRANSACTION_DIRECTORY,
    failed_transaction_directory_name,
    load_failed_transaction_generated_paths,
    load_failed_transaction_snapshot,
)


RETRY_EVIDENCE_DIRECTORY = "retry-evidence"


@dataclass
class RetryEvidence:
    """What a replay may know about one failed implementation attempt."""

    task_id: str
    authored_files: dict[str, str] = field(default_factory=dict)
    generated_paths: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def contents_available(self) -> bool:
        """Whether the authored contents survived, not just their paths."""

        return bool(self.authored_files)

    @property
    def is_empty(self) -> bool:
        return not (
            self.authored_files
            or self.generated_paths
            or self.paths
        )


# --------------------------------------------------------------------------
# State accessors
# --------------------------------------------------------------------------


def _developer_result(
    state: dict[str, Any],
) -> dict[str, Any]:
    agents = state.get("agents")

    if not isinstance(agents, dict):
        return {}

    developer = agents.get("developer")

    if not isinstance(developer, dict):
        return {}

    last_result = developer.get("last_result")

    return last_result if isinstance(last_result, dict) else {}


def state_failed_task_id(
    state: dict[str, Any],
) -> str:
    """Return the failed task the persisted state refers to, if any."""

    value = _developer_result(state).get("failed_task_id")

    return value.strip() if isinstance(value, str) else ""


def state_failed_attempt_paths(
    state: dict[str, Any],
    task_id: str,
) -> list[str]:
    """Return the paths a failed attempt authored, from the state alone.

    This is the zero-storage fallback. It never reads the workspace: the
    files it names were rolled back, so requiring them to exist would always
    return nothing.
    """

    if not task_id:
        return []

    results = _developer_result(state).get("implementation_results")

    if not isinstance(results, list):
        return []

    for item in results:
        if not isinstance(item, dict) or item.get("task_id") != task_id:
            continue

        return [
            path.replace("\\", "/")
            for path in item.get("files", [])
            if isinstance(path, str) and path.strip()
        ]

    return []


# --------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------


def bound_authored_files(
    files: dict[str, str],
) -> tuple[dict[str, str], bool]:
    """Keep only what a retry prompt could ever consume.

    Storing more would grow every checkpoint for content the prompt budget
    discards anyway. Paths are walked in sorted order so the stored result
    does not depend on the order the runtime happened to produce.
    """

    bounded: dict[str, str] = {}
    used = 0
    truncated = False

    for path in sorted(files):
        content = files[path]

        if used >= MAX_FAILED_ATTEMPT_TOTAL_CHARS:
            truncated = True
            continue

        limit = min(
            MAX_FAILED_ATTEMPT_FILE_CHARS,
            MAX_FAILED_ATTEMPT_TOTAL_CHARS - used,
        )

        if len(content) > limit:
            content = content[:limit]
            truncated = True

        bounded[path] = content
        used += len(content)

    return bounded, truncated


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------


def collect_retry_evidence(
    project_root: Path,
    state: dict[str, Any],
) -> RetryEvidence | None:
    """Collect the evidence belonging to the failed task this state names.

    Returns None when the state references no failed task: there is then no
    moment to explain, and nothing is stored.
    """

    task_id = state_failed_task_id(state)

    if not task_id:
        return None

    project_root = Path(project_root)

    authored, truncated = bound_authored_files(
        load_failed_transaction_snapshot(
            project_root=project_root,
            task_id=task_id,
        )
    )

    generated = load_failed_transaction_generated_paths(
        project_root=project_root,
        task_id=task_id,
    )

    evidence = RetryEvidence(
        task_id=task_id,
        authored_files=authored,
        generated_paths=list(generated),
        paths=sorted(authored)
        or state_failed_attempt_paths(state, task_id),
        truncated=truncated,
    )

    return None if evidence.is_empty else evidence


def _evidence_root(
    checkpoint_root: Path,
    task_id: str,
) -> Path:
    return (
        Path(checkpoint_root)
        / RETRY_EVIDENCE_DIRECTORY
        / failed_transaction_directory_name(task_id)
    )


def write_retry_evidence(
    checkpoint_root: Path,
    evidence: RetryEvidence,
) -> Path:
    """Store one attempt's evidence under the checkpoint that explains it.

    The layout is the one the runtime already reads, so a restore is a plain
    copy rather than a second format nobody else understands.
    """

    root = _evidence_root(checkpoint_root, evidence.task_id)

    if root.exists():
        shutil.rmtree(root, ignore_errors=True)

    root.mkdir(parents=True, exist_ok=True)

    files_root = root / "files"

    for relative, content in evidence.authored_files.items():
        target = files_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    (root / "generated-artifacts.txt").write_text(
        "\n".join(sorted(evidence.generated_paths)),
        encoding="utf-8",
    )

    return root


def checkpoint_retry_evidence_task_ids(
    checkpoint_root: Path,
) -> list[str]:
    """Return the directory names of the evidence a checkpoint owns."""

    store = Path(checkpoint_root) / RETRY_EVIDENCE_DIRECTORY

    if not store.is_dir():
        return []

    return sorted(
        item.name
        for item in store.iterdir()
        if item.is_dir()
    )


# --------------------------------------------------------------------------
# Restore
# --------------------------------------------------------------------------


def purge_live_retry_evidence(
    project_root: Path,
) -> None:
    """Discard failed-transaction snapshots left by any later execution.

    They describe runs that happened after the checkpoint being restored, so
    letting them survive would hand a replay the diagnostics of a future it
    is not reproducing.
    """

    shutil.rmtree(
        Path(project_root) / FAILED_TRANSACTION_DIRECTORY,
        ignore_errors=True,
    )


def restore_retry_evidence(
    project_root: Path,
    checkpoint_root: Path,
) -> list[str]:
    """Write back only the evidence this checkpoint owns.

    Called after the stale live evidence has been purged, so what remains is
    exactly the evidence describing the restored moment.
    """

    store = Path(checkpoint_root) / RETRY_EVIDENCE_DIRECTORY

    if not store.is_dir():
        return []

    target_root = Path(project_root) / FAILED_TRANSACTION_DIRECTORY
    restored: list[str] = []

    for source in sorted(store.iterdir()):
        if not source.is_dir():
            continue

        target = target_root / source.name

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        target.parent.mkdir(parents=True, exist_ok=True)

        shutil.copytree(source, target)

        restored.append(source.name)

    return restored


# --------------------------------------------------------------------------
# Runtime resolution
# --------------------------------------------------------------------------


def resolve_failed_attempt_evidence(
    project_root: Path,
    state: dict[str, Any],
    task_id: str,
) -> RetryEvidence:
    """Return the best evidence available about a failed attempt.

    Durable contents win. When they are gone - a checkpoint taken before
    they were preserved, or a snapshot removed for any other reason - the
    paths the state recorded still explain what was tried, and the caller is
    told that only the structure survived.
    """

    project_root = Path(project_root)

    authored = load_failed_transaction_snapshot(
        project_root=project_root,
        task_id=task_id,
    )

    generated = load_failed_transaction_generated_paths(
        project_root=project_root,
        task_id=task_id,
    )

    if authored:
        return RetryEvidence(
            task_id=task_id,
            authored_files=authored,
            generated_paths=list(generated),
            paths=sorted(authored),
        )

    return RetryEvidence(
        task_id=task_id,
        authored_files={},
        generated_paths=list(generated),
        paths=state_failed_attempt_paths(state, task_id),
    )
