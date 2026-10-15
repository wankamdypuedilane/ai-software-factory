"""Reproducible workflow milestones.

A checkpoint captures a coherent point of the workflow - state, configuration,
approved artifacts and promoted source - so that one phase can be replayed
without paying for the phases that precede it.

It is deliberately distinct from `WorkspaceTransaction`: a transaction
protects one implementation unit during its execution, a checkpoint records a
milestone the operator can return to.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ai_factory.workspace_transaction import (
    FAILED_TRANSACTION_DIRECTORY,
)
from ai_factory.retry_evidence import (
    collect_retry_evidence,
    purge_live_retry_evidence,
    restore_retry_evidence,
    write_retry_evidence,
)
from ai_factory.state import load_state, save_state


CHECKPOINT_FORMAT_VERSION = 1

CHECKPOINT_DIRECTORY = "checkpoints"

CHECKPOINT_METADATA_FILE = "checkpoint.yaml"

CHECKPOINT_FILES_DIRECTORY = "files"

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


# Derived, vendored or ephemeral. None of it defines the milestone, and
# node_modules alone would make every checkpoint hundreds of megabytes.
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".cache",
        ".parcel-cache",
        "dist",
        "build",
        "out",
        "coverage",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
    }
)

# Factory-owned directories that are never part of a milestone: the
# checkpoint store itself, and the diagnostics of failed attempts.
EXCLUDED_FACTORY_SUBDIRECTORIES = (
    "checkpoints",
    "failed-transactions",
)

DEPENDENCY_MANIFESTS = (
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)


class CheckpointError(ValueError):
    """A checkpoint could not be created, found or read."""


class IncompatibleCheckpointError(CheckpointError):
    """The checkpoint does not belong to this project or this engine."""


@dataclass
class CheckpointMetadata:
    name: str
    format_version: int
    project_id: str
    project_name: str
    created_at: str
    phase: str
    agent_statuses: dict[str, str] = field(default_factory=dict)
    engine_fingerprint: str = ""
    dependency_fingerprint: str = ""
    file_count: int = 0
    # Optional, so a checkpoint written before retry evidence existed still
    # deserializes and still restores. Its absence means the replay falls
    # back to the paths the state recorded.
    retry_evidence_task_id: str = ""


@dataclass
class RestoreReport:
    metadata: CheckpointMetadata
    restored_files: int
    dependencies_compatible: bool


# --------------------------------------------------------------------------
# Fingerprints
# --------------------------------------------------------------------------


def compute_engine_fingerprint() -> str:
    """Identify the engine build without requiring a version control system.

    Hashes the engine's own sources, so a checkpoint taken before an
    incompatible change is recognised as such even outside a repository.
    """

    package_root = Path(__file__).resolve().parent

    digest = hashlib.sha256()

    for path in sorted(package_root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))

        try:
            digest.update(path.read_bytes())
        except OSError:
            continue

    return digest.hexdigest()


def compute_dependency_fingerprint(
    project_root: Path,
) -> str:
    """Fingerprint the manifests that determine the dependency state."""

    digest = hashlib.sha256()

    for name in DEPENDENCY_MANIFESTS:
        path = project_root / name

        if not path.is_file():
            continue

        digest.update(name.encode("utf-8"))

        try:
            digest.update(path.read_bytes())
        except OSError:
            continue

    return digest.hexdigest()


# --------------------------------------------------------------------------
# Managed files
# --------------------------------------------------------------------------


def validate_checkpoint_name(
    name: Any,
) -> str:
    """Validate a checkpoint name, refusing anything that escapes the store."""

    if not isinstance(name, str) or not _NAME_PATTERN.match(name.strip()):
        raise CheckpointError(
            "Checkpoint name must be 1-64 characters of letters, digits, "
            f"dot, dash or underscore: {name!r}"
        )

    return name.strip()


def _is_excluded(
    relative: str,
) -> bool:
    parts = relative.split("/")

    if any(part in EXCLUDED_DIRECTORIES for part in parts):
        return True

    return (
        len(parts) >= 2
        and parts[0] == ".factory"
        and parts[1] in EXCLUDED_FACTORY_SUBDIRECTORIES
    )


def iter_managed_files(
    root: Path,
) -> list[str]:
    """Return every project-relative file a checkpoint governs."""

    managed: list[str] = []

    for current, directories, filenames in os.walk(root):
        current_path = Path(current)

        relative_dir = (
            current_path.relative_to(root).as_posix()
            if current_path != root
            else ""
        )

        directories[:] = [
            name
            for name in directories
            if not _is_excluded(
                f"{relative_dir}/{name}".lstrip("/")
            )
        ]

        for filename in filenames:
            relative = (
                f"{relative_dir}/{filename}".lstrip("/")
            )

            if not _is_excluded(relative):
                managed.append(relative)

    return sorted(managed)


def _checkpoint_root(
    project_root: Path,
    name: str,
) -> Path:
    return (
        project_root
        / ".factory"
        / CHECKPOINT_DIRECTORY
        / name
    )


def _serialize(
    metadata: CheckpointMetadata,
) -> dict[str, Any]:
    return {
        "name": metadata.name,
        "format_version": metadata.format_version,
        "project_id": metadata.project_id,
        "project_name": metadata.project_name,
        "created_at": metadata.created_at,
        "phase": metadata.phase,
        "agent_statuses": dict(metadata.agent_statuses),
        "engine_fingerprint": metadata.engine_fingerprint,
        "dependency_fingerprint": metadata.dependency_fingerprint,
        "file_count": metadata.file_count,
        "retry_evidence_task_id": metadata.retry_evidence_task_id,
    }


def _deserialize(
    payload: dict[str, Any],
) -> CheckpointMetadata:
    return CheckpointMetadata(
        name=str(payload.get("name", "")),
        format_version=int(payload.get("format_version", 0)),
        project_id=str(payload.get("project_id", "")),
        project_name=str(payload.get("project_name", "")),
        created_at=str(payload.get("created_at", "")),
        phase=str(payload.get("phase", "")),
        agent_statuses=dict(payload.get("agent_statuses") or {}),
        engine_fingerprint=str(payload.get("engine_fingerprint", "")),
        dependency_fingerprint=str(
            payload.get("dependency_fingerprint", "")
        ),
        file_count=int(payload.get("file_count", 0)),
        retry_evidence_task_id=str(
            payload.get("retry_evidence_task_id", "")
        ),
    )


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


def create_checkpoint(
    project_root: Path,
    name: str,
) -> CheckpointMetadata:
    """Capture the current milestone under a name."""

    name = validate_checkpoint_name(name)

    project_root = Path(project_root)
    state_path = project_root / ".factory" / "state.yaml"

    if not state_path.is_file():
        raise CheckpointError(
            "Project state not found; run this inside a Factory project."
        )

    state = load_state(state_path)
    project = state.get("project", {})

    managed = iter_managed_files(project_root)

    root = _checkpoint_root(project_root, name)

    if root.exists():
        shutil.rmtree(root, ignore_errors=True)

    files_root = root / CHECKPOINT_FILES_DIRECTORY

    for relative in managed:
        target = files_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            project_root / relative,
            target,
        )

    # The milestone is not only its files: when the state names a failed
    # task, the evidence explaining that failure belongs to this moment too.
    # It is stored under the checkpoint rather than left in the runtime
    # scratch directory, which any later execution may overwrite or purge.
    evidence = collect_retry_evidence(project_root, state)

    if evidence is not None:
        write_retry_evidence(root, evidence)

    metadata = CheckpointMetadata(
        name=name,
        format_version=CHECKPOINT_FORMAT_VERSION,
        project_id=str(project.get("id", "")),
        project_name=str(project.get("name", "")),
        created_at=datetime.now(timezone.utc).isoformat(
            timespec="seconds",
        ),
        phase=str(project.get("phase", "")),
        agent_statuses={
            agent_name: str(agent.get("status", ""))
            for agent_name, agent in (
                state.get("agents") or {}
            ).items()
            if isinstance(agent, dict)
        },
        engine_fingerprint=compute_engine_fingerprint(),
        dependency_fingerprint=compute_dependency_fingerprint(
            project_root
        ),
        file_count=len(managed),
        retry_evidence_task_id=(
            evidence.task_id if evidence is not None else ""
        ),
    )

    root.mkdir(parents=True, exist_ok=True)
    save_state(
        root / CHECKPOINT_METADATA_FILE,
        _serialize(metadata),
    )

    return metadata


def list_checkpoints(
    project_root: Path,
) -> list[CheckpointMetadata]:
    """Return every checkpoint stored for this project, newest first."""

    store = (
        Path(project_root)
        / ".factory"
        / CHECKPOINT_DIRECTORY
    )

    if not store.is_dir():
        return []

    found: list[CheckpointMetadata] = []

    for directory in sorted(store.iterdir()):
        metadata_path = directory / CHECKPOINT_METADATA_FILE

        if not metadata_path.is_file():
            continue

        try:
            found.append(
                _deserialize(load_state(metadata_path))
            )
        except (OSError, ValueError):
            continue

    return sorted(
        found,
        key=lambda item: item.created_at,
        reverse=True,
    )


def read_checkpoint(
    project_root: Path,
    name: str,
) -> CheckpointMetadata:
    name = validate_checkpoint_name(name)

    metadata_path = (
        _checkpoint_root(Path(project_root), name)
        / CHECKPOINT_METADATA_FILE
    )

    if not metadata_path.is_file():
        raise CheckpointError(
            f"Checkpoint not found: {name}"
        )

    return _deserialize(load_state(metadata_path))


def _assert_compatible(
    project_root: Path,
    metadata: CheckpointMetadata,
    allow_engine_change: bool,
) -> None:
    if metadata.format_version != CHECKPOINT_FORMAT_VERSION:
        raise IncompatibleCheckpointError(
            "Checkpoint format "
            f"{metadata.format_version} cannot be read by this engine "
            f"(expected {CHECKPOINT_FORMAT_VERSION})."
        )

    state = load_state(
        project_root / ".factory" / "state.yaml"
    )

    project_id = str(
        (state.get("project") or {}).get("id", "")
    )

    if metadata.project_id != project_id:
        raise IncompatibleCheckpointError(
            "Checkpoint belongs to a different project: "
            f"{metadata.project_id!r} != {project_id!r}"
        )

    if (
        not allow_engine_change
        and metadata.engine_fingerprint != compute_engine_fingerprint()
    ):
        raise IncompatibleCheckpointError(
            "Checkpoint was created by a different engine build. "
            "Restoring it could reproduce a state this engine no longer "
            "understands. Re-create it, or restore with the explicit "
            "engine-change option."
        )


def restore_checkpoint(
    project_root: Path,
    name: str,
    allow_engine_change: bool = False,
) -> RestoreReport:
    """Return the project to a milestone, all of it or none of it.

    The current managed files are moved aside first. The checkpoint is then
    written; any failure puts the original files back, so the workspace and
    the state are never half-restored.
    """

    project_root = Path(project_root)

    metadata = read_checkpoint(project_root, name)

    _assert_compatible(
        project_root,
        metadata,
        allow_engine_change,
    )

    current_fingerprint = compute_dependency_fingerprint(
        project_root
    )

    files_root = (
        _checkpoint_root(project_root, metadata.name)
        / CHECKPOINT_FILES_DIRECTORY
    )

    checkpoint_files = iter_managed_files(files_root)
    current_files = iter_managed_files(project_root)

    backup_root = Path(
        tempfile.mkdtemp(prefix="ai-factory-restore-")
    )

    evidence_backup = backup_root / "retry-evidence-before-restore"

    live_evidence = (
        project_root / FAILED_TRANSACTION_DIRECTORY
    )

    try:
        for relative in current_files:
            target = backup_root / "files" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(
                project_root / relative,
                target,
            )

        # Retry evidence is not a managed file, so it needs its own copy for
        # the rollback path: a failed restore must leave the run that is
        # still current with the diagnostics it had.
        if live_evidence.is_dir():
            shutil.copytree(live_evidence, evidence_backup)

        for relative in current_files:
            (project_root / relative).unlink(missing_ok=True)

        for relative in checkpoint_files:
            target = project_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(
                files_root / relative,
                target,
            )

        # Diagnostics on disk belong to executions that happened after this
        # checkpoint. Leaving them would let a replay inherit the evidence
        # of a future it is not reproducing.
        purge_live_retry_evidence(project_root)

        # Only then does the checkpoint write back the evidence it owns,
        # which describes the very moment being restored.
        restore_retry_evidence(
            project_root=project_root,
            checkpoint_root=_checkpoint_root(project_root, metadata.name),
        )

    except BaseException:
        # Put every managed file back exactly as it was.
        for relative in current_files:
            source = backup_root / "files" / relative

            if not source.is_file():
                continue

            target = project_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copyfile(str(source), str(target))
            except OSError:
                os.replace(str(source), str(target))

        shutil.rmtree(live_evidence, ignore_errors=True)

        if evidence_backup.is_dir():
            shutil.copytree(evidence_backup, live_evidence)

        raise

    finally:
        shutil.rmtree(backup_root, ignore_errors=True)

    return RestoreReport(
        metadata=metadata,
        restored_files=len(checkpoint_files),
        dependencies_compatible=(
            current_fingerprint == metadata.dependency_fingerprint
        ),
    )
