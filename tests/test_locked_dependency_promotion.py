from pathlib import Path

from ai_factory import workspace_transaction
from ai_factory.workspace_transaction import _copy_over, _rename_with_retries


def test_a_locked_directory_is_retried_then_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_transaction, "RENAME_DELAY_SECONDS", 0)
    calls = {"count": 0}

    def locked(self, target):
        calls["count"] += 1
        raise PermissionError(5, "Accès refusé")

    monkeypatch.setattr(Path, "rename", locked)

    assert _rename_with_retries(tmp_path / "node_modules", tmp_path / "prev") is False
    assert calls["count"] == workspace_transaction.RENAME_ATTEMPTS


def test_a_transient_lock_is_waited_out(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_transaction, "RENAME_DELAY_SECONDS", 0)
    source = tmp_path / "node_modules"
    source.mkdir()
    real_rename = Path.rename
    calls = {"count": 0}

    def flaky(self, target):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError(5, "Accès refusé")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)

    assert _rename_with_retries(source, tmp_path / "prev") is True
    assert (tmp_path / "prev").is_dir()


def test_copy_over_updates_files_in_place(tmp_path: Path) -> None:
    source = tmp_path / "isolated" / "node_modules"
    (source / "pg").mkdir(parents=True)
    (source / "pg" / "index.js").write_text("new", encoding="utf-8")
    (source / "new-pkg").mkdir()
    (source / "new-pkg" / "index.js").write_text("added", encoding="utf-8")
    target = tmp_path / "project" / "node_modules"
    (target / "pg").mkdir(parents=True)
    (target / "pg" / "index.js").write_text("old", encoding="utf-8")

    _copy_over(source, target)

    assert (target / "pg" / "index.js").read_text(encoding="utf-8") == "new"
    assert (target / "new-pkg" / "index.js").read_text(encoding="utf-8") == "added"
