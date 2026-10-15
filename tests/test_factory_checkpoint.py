"""Reproducible workflow milestones.

Replaying a Developer bug used to cost a full Product/UX/Architect run:
127 provider calls and ~38 minutes in LinkVault round 5. A checkpoint
captures the milestone so only the phase under test is replayed.
"""

from pathlib import Path

import pytest

from ai_factory.factory_checkpoint import (
    CHECKPOINT_FORMAT_VERSION,
    CheckpointError,
    IncompatibleCheckpointError,
    compute_dependency_fingerprint,
    compute_engine_fingerprint,
    create_checkpoint,
    list_checkpoints,
    restore_checkpoint,
)
from ai_factory.orchestrator import get_next_agent
from ai_factory.project import initialize_project
from ai_factory.state import load_state, save_state


def _before_developer(tmp_path: Path) -> Path:
    """A project sitting exactly at the Developer milestone."""

    project_root = initialize_project("LinkVault", tmp_path)

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)

    for agent in ("product", "ux_ui", "architect"):
        state["agents"][agent] = {
            "status": "APPROVED",
            "last_result": {
                "status": "COMPLETED",
                "summary": f"{agent} completed.",
                "generated_artifacts": [],
            },
        }

    state["agents"]["developer"] = {"status": "READY"}
    state["project"]["phase"] = "implementation"
    state["approvals"]["product_scope"] = True
    state["approvals"]["design"] = True
    state["approvals"]["architecture"] = True
    state["design_gate"] = {
        "status": "APPROVED",
        "groups": {"deliverables": {"approved": 3, "total": 3}},
        "external_blockers": [],
        "human_approval": True,
    }
    state["technology_gate"] = {
        "status": "APPROVED",
        "human_approval": True,
        "proposal": {"components": {"backend": {"technology": "Fastify"}}},
    }

    save_state(state_path, state)

    for relative, content in (
        ("knowledge/project/requirements.md", "# Requirements\n"),
        ("knowledge/architecture/api.md", "# API\n"),
        ("workflows/backlog/user-stories.md", "# Stories\n"),
        ("package.json", '{"name":"linkvault"}'),
        ("package-lock.json", '{"lockfileVersion":3}'),
        ("src/app.ts", "export const app = 1;\n"),
    ):
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    return project_root


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------


def test_a_checkpoint_captures_the_milestone(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)

    metadata = create_checkpoint(project_root, "before-developer")

    assert metadata.name == "before-developer"
    assert metadata.format_version == CHECKPOINT_FORMAT_VERSION
    assert metadata.project_id == "linkvault"
    assert metadata.phase == "implementation"
    assert metadata.agent_statuses["developer"] == "READY"
    assert metadata.engine_fingerprint == compute_engine_fingerprint()
    assert metadata.dependency_fingerprint == (
        compute_dependency_fingerprint(project_root)
    )


def test_checkpoints_can_be_listed(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)

    create_checkpoint(project_root, "before-developer")
    create_checkpoint(project_root, "after-foundation")

    names = [item.name for item in list_checkpoints(project_root)]

    assert sorted(names) == ["after-foundation", "before-developer"]


def test_dependencies_are_not_copied_into_the_checkpoint(
    tmp_path: Path,
) -> None:
    project_root = _before_developer(tmp_path)

    package = project_root / "node_modules" / "prisma"
    package.mkdir(parents=True)
    (package / "index.js").write_text("x", encoding="utf-8")

    create_checkpoint(project_root, "before-developer")

    store = (
        project_root / ".factory" / "checkpoints" / "before-developer"
    )

    assert not (store / "files" / "node_modules").exists()


def test_failed_transactions_never_enter_a_checkpoint(
    tmp_path: Path,
) -> None:
    project_root = _before_developer(tmp_path)

    snapshot = (
        project_root
        / ".factory"
        / "failed-transactions"
        / "LV-DEV-002"
        / "files"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "broken.ts").write_text("boom", encoding="utf-8")

    create_checkpoint(project_root, "before-developer")

    store = (
        project_root / ".factory" / "checkpoints" / "before-developer"
    )

    assert not (
        store / "files" / ".factory" / "failed-transactions"
    ).exists()


def test_restoring_clears_diagnostics_of_the_discarded_run(
    tmp_path: Path,
) -> None:
    """A restored run must not inherit a stale failed attempt."""

    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    snapshot = (
        project_root
        / ".factory"
        / "failed-transactions"
        / "LV-DEV-002"
        / "files"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "attempt.ts").write_text("boom", encoding="utf-8")

    restore_checkpoint(project_root, "before-developer")

    assert not (
        project_root / ".factory" / "failed-transactions"
    ).exists()


@pytest.mark.parametrize(
    "name",
    ["../escape", "a/b", "..", "", "  ", "C:/absolute"],
)
def test_an_unsafe_checkpoint_name_is_refused(
    tmp_path: Path,
    name: str,
) -> None:
    project_root = _before_developer(tmp_path)

    with pytest.raises(CheckpointError):
        create_checkpoint(project_root, name)


# --------------------------------------------------------------------------
# Restore
# --------------------------------------------------------------------------


def test_workspace_changes_are_reverted(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    (project_root / "src" / "app.ts").write_text(
        "export const app = 'DEVELOPER';\n",
        encoding="utf-8",
    )
    (project_root / "src" / "extra.ts").write_text(
        "export const extra = true;\n",
        encoding="utf-8",
    )

    restore_checkpoint(project_root, "before-developer")

    assert (project_root / "src" / "app.ts").read_text(
        encoding="utf-8",
    ) == "export const app = 1;\n"
    assert not (project_root / "src" / "extra.ts").exists()


def test_state_changes_are_reverted(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["developer"] = {
        "status": "FAILED",
        "last_result": {"replan_count": 3},
    }
    save_state(state_path, state)

    restore_checkpoint(project_root, "before-developer")

    restored = load_state(state_path)

    assert restored["agents"]["developer"]["status"] == "READY"
    assert restored["project"]["phase"] == "implementation"


def test_the_milestone_is_reproducible(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["developer"]["status"] = "FAILED"
    state["design_gate"]["status"] = "PARTIAL"
    save_state(state_path, state)

    restore_checkpoint(project_root, "before-developer")

    restored = load_state(state_path)

    assert get_next_agent(restored) == "developer"
    assert restored["project"]["phase"] == "implementation"
    assert restored["design_gate"]["status"] == "APPROVED"
    assert restored["technology_gate"]["status"] == "APPROVED"
    assert restored["agents"]["developer"]["status"] == "READY"
    assert restored["approvals"]["architecture"] is True

    assert (
        project_root / "knowledge" / "architecture" / "api.md"
    ).read_text(encoding="utf-8") == "# API\n"


def test_restoring_twice_is_deterministic(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    restore_checkpoint(project_root, "before-developer")
    first = sorted(
        path.relative_to(project_root).as_posix()
        for path in project_root.rglob("*")
        if path.is_file() and ".factory/checkpoints" not in
        path.relative_to(project_root).as_posix()
    )

    restore_checkpoint(project_root, "before-developer")
    second = sorted(
        path.relative_to(project_root).as_posix()
        for path in project_root.rglob("*")
        if path.is_file() and ".factory/checkpoints" not in
        path.relative_to(project_root).as_posix()
    )

    assert first == second


def test_a_failed_restore_leaves_everything_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    (project_root / "src" / "app.ts").write_text(
        "export const app = 'MODIFIED';\n",
        encoding="utf-8",
    )

    state_before = (
        project_root / ".factory" / "state.yaml"
    ).read_text(encoding="utf-8")

    import ai_factory.factory_checkpoint as module

    def exploding_copy(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.shutil, "copyfile", exploding_copy)

    with pytest.raises(OSError):
        restore_checkpoint(project_root, "before-developer")

    # Neither half was applied.
    assert (project_root / "src" / "app.ts").read_text(
        encoding="utf-8",
    ) == "export const app = 'MODIFIED';\n"
    assert (
        project_root / ".factory" / "state.yaml"
    ).read_text(encoding="utf-8") == state_before


# --------------------------------------------------------------------------
# Compatibility
# --------------------------------------------------------------------------


def test_a_checkpoint_from_another_project_is_refused(
    tmp_path: Path,
) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["project"]["id"] = "shoplite"
    save_state(state_path, state)

    with pytest.raises(
        IncompatibleCheckpointError,
        match="different project",
    ):
        restore_checkpoint(project_root, "before-developer")


def test_a_checkpoint_from_another_engine_is_refused(
    tmp_path: Path,
) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    metadata_path = (
        project_root
        / ".factory"
        / "checkpoints"
        / "before-developer"
        / "checkpoint.yaml"
    )
    metadata = load_state(metadata_path)
    metadata["engine_fingerprint"] = "0" * 64
    save_state(metadata_path, metadata)

    with pytest.raises(
        IncompatibleCheckpointError,
        match="engine",
    ):
        restore_checkpoint(project_root, "before-developer")

    # Explicit opt-in still allows it.
    report = restore_checkpoint(
        project_root,
        "before-developer",
        allow_engine_change=True,
    )

    assert report.metadata.name == "before-developer"


def test_an_unknown_format_version_is_refused(tmp_path: Path) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    metadata_path = (
        project_root
        / ".factory"
        / "checkpoints"
        / "before-developer"
        / "checkpoint.yaml"
    )
    metadata = load_state(metadata_path)
    metadata["format_version"] = CHECKPOINT_FORMAT_VERSION + 99
    save_state(metadata_path, metadata)

    with pytest.raises(
        IncompatibleCheckpointError,
        match="format",
    ):
        restore_checkpoint(project_root, "before-developer")


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------


def test_unchanged_manifests_keep_the_dependencies(
    tmp_path: Path,
) -> None:
    project_root = _before_developer(tmp_path)

    package = project_root / "node_modules" / "prisma"
    package.mkdir(parents=True)
    (package / "index.js").write_text("x", encoding="utf-8")

    create_checkpoint(project_root, "before-developer")

    report = restore_checkpoint(project_root, "before-developer")

    assert report.dependencies_compatible is True
    assert (package / "index.js").is_file()


def test_changed_manifests_are_reported_as_stale(
    tmp_path: Path,
) -> None:
    project_root = _before_developer(tmp_path)
    create_checkpoint(project_root, "before-developer")

    (project_root / "package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{"zod":"3.24.1"}}',
        encoding="utf-8",
    )

    report = restore_checkpoint(project_root, "before-developer")

    assert report.dependencies_compatible is False
