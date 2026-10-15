from pathlib import Path

import pytest

from ai_factory.workspace_transaction import (
    PromotionConflictError,
    open_workspace_transaction,
)


def _seed(
    root: Path,
) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.ts").write_text(
        "export const app = 1;\n",
        encoding="utf-8",
    )
    (root / "src" / "untouched.ts").write_text(
        "export const untouched = true;\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"name":"demo"}',
        encoding="utf-8",
    )


def test_transaction_copies_the_source_tree(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        assert (
            transaction.root / "src" / "app.ts"
        ).read_text(encoding="utf-8") == "export const app = 1;\n"

        assert transaction.root != tmp_path


def test_transaction_excludes_heavy_and_factory_directories(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    for name in (
        ".git",
        ".factory",
        ".next",
        "dist",
        "coverage",
        "__pycache__",
    ):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "payload.txt").write_text(
            "heavy",
            encoding="utf-8",
        )

    with open_workspace_transaction(tmp_path) as transaction:
        for name in (
            ".git",
            ".factory",
            ".next",
            "dist",
            "coverage",
            "__pycache__",
        ):
            assert not (
                transaction.root / name
            ).exists()


def test_discard_leaves_the_source_untouched(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        (
            transaction.root / "src" / "app.ts"
        ).write_text(
            "export const app = 999;\n",
            encoding="utf-8",
        )
        (
            transaction.root / "src" / "created.ts"
        ).write_text(
            "export const created = true;\n",
            encoding="utf-8",
        )

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(encoding="utf-8") == "export const app = 1;\n"

    assert not (
        tmp_path / "src" / "created.ts"
    ).exists()


def test_promote_applies_created_and_modified_files(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        (
            transaction.root / "src" / "app.ts"
        ).write_text(
            "export const app = 2;\n",
            encoding="utf-8",
        )
        (
            transaction.root / "src" / "created.ts"
        ).write_text(
            "export const created = true;\n",
            encoding="utf-8",
        )

        promoted = transaction.promote()

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(encoding="utf-8") == "export const app = 2;\n"

    assert (
        tmp_path / "src" / "created.ts"
    ).read_text(encoding="utf-8") == "export const created = true;\n"

    assert sorted(promoted) == [
        "src/app.ts",
        "src/created.ts",
    ]


def test_promote_leaves_unrelated_files_strictly_intact(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    original = (
        tmp_path / "src" / "untouched.ts"
    ).read_text(encoding="utf-8")

    with open_workspace_transaction(tmp_path) as transaction:
        (
            transaction.root / "src" / "app.ts"
        ).write_text(
            "export const app = 3;\n",
            encoding="utf-8",
        )

        transaction.promote()

    assert (
        tmp_path / "src" / "untouched.ts"
    ).read_text(encoding="utf-8") == original


def test_external_change_to_an_unrelated_file_is_preserved(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        (
            transaction.root / "src" / "app.ts"
        ).write_text(
            "export const app = 4;\n",
            encoding="utf-8",
        )

        # An unrelated external write lands while the task runs.
        (
            tmp_path / "src" / "untouched.ts"
        ).write_text(
            "export const untouched = 'external';\n",
            encoding="utf-8",
        )

        transaction.promote()

    assert (
        tmp_path / "src" / "untouched.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const untouched = 'external';\n"

    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(encoding="utf-8") == "export const app = 4;\n"


def test_external_change_to_a_promoted_file_fails_safely(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        (
            transaction.root / "src" / "app.ts"
        ).write_text(
            "export const app = 5;\n",
            encoding="utf-8",
        )
        (
            transaction.root / "src" / "created.ts"
        ).write_text(
            "export const created = true;\n",
            encoding="utf-8",
        )

        (
            tmp_path / "src" / "app.ts"
        ).write_text(
            "export const app = 'external';\n",
            encoding="utf-8",
        )

        with pytest.raises(
            PromotionConflictError,
            match="src/app.ts",
        ):
            transaction.promote()

    # Nothing was promoted: the conflict aborts the whole promotion.
    assert (
        tmp_path / "src" / "app.ts"
    ).read_text(
        encoding="utf-8",
    ) == "export const app = 'external';\n"

    assert not (
        tmp_path / "src" / "created.ts"
    ).exists()


def test_dependencies_are_shared_when_no_setup_command_mutates_them(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    modules = tmp_path / "node_modules" / "left-pad"
    modules.mkdir(parents=True)
    (modules / "index.js").write_text(
        "module.exports = 1;\n",
        encoding="utf-8",
    )

    with open_workspace_transaction(tmp_path) as transaction:
        assert transaction.shared_directories == (
            "node_modules",
        )

        assert (
            transaction.root
            / "node_modules"
            / "left-pad"
            / "index.js"
        ).is_file()


def test_dependencies_are_isolated_when_a_setup_command_mutates_them(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    modules = tmp_path / "node_modules" / "left-pad"
    modules.mkdir(parents=True)
    (modules / "index.js").write_text(
        "module.exports = 1;\n",
        encoding="utf-8",
    )

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) as transaction:
        assert transaction.shared_directories == ()

        assert not (
            transaction.root / "node_modules"
        ).exists()


def test_changed_files_reports_the_transaction_diff(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        (
            transaction.root / "src" / "app.ts"
        ).write_text(
            "export const app = 6;\n",
            encoding="utf-8",
        )
        (
            transaction.root / "src" / "created.ts"
        ).write_text(
            "export const created = true;\n",
            encoding="utf-8",
        )

        changed = transaction.changed_files()

    assert changed == {
        "src/app.ts": "export const app = 6;\n",
        "src/created.ts": "export const created = true;\n",
    }


def test_transaction_directory_is_removed_after_use(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        root = transaction.root
        assert root.is_dir()

    assert not root.exists()


def test_discarding_a_transaction_never_deletes_shared_dependencies(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    package = tmp_path / "node_modules" / "left-pad"
    package.mkdir(parents=True)
    (package / "index.js").write_text(
        "module.exports = 1;\n",
        encoding="utf-8",
    )

    with open_workspace_transaction(tmp_path) as transaction:
        assert transaction.shared_directories == (
            "node_modules",
        )

    assert (
        tmp_path
        / "node_modules"
        / "left-pad"
        / "index.js"
    ).read_text(
        encoding="utf-8",
    ) == "module.exports = 1;\n"


def test_isolated_dependencies_are_promoted_on_success(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    stale = tmp_path / "node_modules" / "stale"
    stale.mkdir(parents=True)
    (stale / "index.js").write_text(
        "module.exports = 'stale';\n",
        encoding="utf-8",
    )

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) as transaction:
        installed = (
            transaction.root / "node_modules" / "fresh"
        )
        installed.mkdir(parents=True)
        (installed / "index.js").write_text(
            "module.exports = 'fresh';\n",
            encoding="utf-8",
        )

        transaction.promote()

    assert (
        tmp_path / "node_modules" / "fresh" / "index.js"
    ).is_file()

    assert not (
        tmp_path / "node_modules" / "stale"
    ).exists()


def test_isolated_dependencies_are_not_promoted_on_failure(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    stale = tmp_path / "node_modules" / "stale"
    stale.mkdir(parents=True)
    (stale / "index.js").write_text(
        "module.exports = 'stale';\n",
        encoding="utf-8",
    )

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) as transaction:
        installed = (
            transaction.root / "node_modules" / "fresh"
        )
        installed.mkdir(parents=True)
        (installed / "index.js").write_text(
            "module.exports = 'fresh';\n",
            encoding="utf-8",
        )

    assert (
        tmp_path / "node_modules" / "stale" / "index.js"
    ).is_file()

    assert not (
        tmp_path / "node_modules" / "fresh"
    ).exists()
