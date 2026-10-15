"""An isolated transaction starts from the workspace's validated dependencies.

LinkVault round 5: a unit declaring only `npm run prisma:generate` got an
isolated but empty dependency directory, so the prisma binary was absent and
the command could never succeed - 46 times.
"""

from pathlib import Path

import pytest

from ai_factory.workspace_transaction import (
    open_workspace_transaction,
    requires_dependency_seed,
)


def _seed_workspace(root: Path, with_dependencies: bool = True) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.ts").write_text(
        "export const app = 1;\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"name":"demo"}',
        encoding="utf-8",
    )
    (root / "prisma").mkdir()
    (root / "prisma" / "schema.prisma").write_text(
        "generator client {}\n",
        encoding="utf-8",
    )

    if with_dependencies:
        binary = root / "node_modules" / ".bin"
        binary.mkdir(parents=True)
        (binary / "prisma.cmd").write_text(
            "@echo prisma\n",
            encoding="utf-8",
        )
        package = root / "node_modules" / "prisma"
        package.mkdir(parents=True)
        (package / "index.js").write_text(
            "module.exports = 'prisma';\n",
            encoding="utf-8",
        )


# --------------------------------------------------------------------------
# Which units need the existing dependencies
# --------------------------------------------------------------------------


def test_a_unit_that_does_not_install_needs_the_existing_dependencies() -> None:
    assert requires_dependency_seed(
        ["npm run prisma:generate"]
    ) is True


def test_a_unit_that_installs_does_not_need_a_seed() -> None:
    assert requires_dependency_seed(
        ["npm install --ignore-scripts"]
    ) is False

    assert requires_dependency_seed(
        ["npm ci --ignore-scripts", "npm run prisma:generate"]
    ) is False


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------


def test_prisma_generate_alone_finds_the_dependencies(
    tmp_path: Path,
) -> None:
    """The exact LinkVault round-5 unit."""

    _seed_workspace(tmp_path)

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm run prisma:generate"],
    ) as transaction:
        assert transaction.isolated_dependencies == ("node_modules",)
        assert transaction.shared_directories == ()

        assert (
            transaction.root
            / "node_modules"
            / ".bin"
            / "prisma.cmd"
        ).is_file()

        assert (
            transaction.root
            / "node_modules"
            / "prisma"
            / "index.js"
        ).is_file()


def test_an_installing_unit_still_starts_from_an_empty_directory(
    tmp_path: Path,
) -> None:
    _seed_workspace(tmp_path)

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm install --ignore-scripts"],
    ) as transaction:
        assert not (
            transaction.root / "node_modules"
        ).exists()


def test_no_dependencies_to_seed_fails_honestly(
    tmp_path: Path,
) -> None:
    _seed_workspace(tmp_path, with_dependencies=False)

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm run prisma:generate"],
    ) as transaction:
        assert not (
            transaction.root / "node_modules"
        ).exists()


def test_a_transaction_without_setup_keeps_sharing(
    tmp_path: Path,
) -> None:
    _seed_workspace(tmp_path)

    with open_workspace_transaction(tmp_path) as transaction:
        assert transaction.shared_directories == ("node_modules",)
        assert transaction.isolated_dependencies == ()


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


def test_a_seeded_dependency_mutation_is_discarded_on_failure(
    tmp_path: Path,
) -> None:
    _seed_workspace(tmp_path)

    original = (
        tmp_path / "node_modules" / "prisma" / "index.js"
    ).read_text(encoding="utf-8")

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm run prisma:generate"],
    ) as transaction:
        generated = (
            transaction.root / "node_modules" / ".prisma" / "client"
        )
        generated.mkdir(parents=True)
        (generated / "index.js").write_text(
            "module.exports = {};\n",
            encoding="utf-8",
        )

        (
            transaction.root / "node_modules" / "prisma" / "index.js"
        ).write_text(
            "module.exports = 'MUTATED';\n",
            encoding="utf-8",
        )

    assert (
        tmp_path / "node_modules" / "prisma" / "index.js"
    ).read_text(encoding="utf-8") == original

    assert not (
        tmp_path / "node_modules" / ".prisma"
    ).exists()


def test_a_seeded_dependency_mutation_is_promoted_on_success(
    tmp_path: Path,
) -> None:
    _seed_workspace(tmp_path)

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm run prisma:generate"],
    ) as transaction:
        generated = (
            transaction.root / "node_modules" / ".prisma" / "client"
        )
        generated.mkdir(parents=True)
        (generated / "index.js").write_text(
            "module.exports = {};\n",
            encoding="utf-8",
        )

        transaction.promote()

    assert (
        tmp_path / "node_modules" / ".prisma" / "client" / "index.js"
    ).is_file()

    # The seeded packages survive the promotion.
    assert (
        tmp_path / "node_modules" / "prisma" / "index.js"
    ).is_file()


def test_the_seed_is_a_copy_not_a_link(
    tmp_path: Path,
) -> None:
    """Nothing writable in the transaction may reach the real workspace."""

    _seed_workspace(tmp_path)

    with open_workspace_transaction(
        tmp_path,
        setup_commands=["npm run prisma:generate"],
    ) as transaction:
        modules = transaction.root / "node_modules"

        assert modules.is_dir()
        assert not modules.is_symlink()

        package = modules / "prisma" / "index.js"

        # Writing in place must not reach the source file.
        package.write_text(
            "module.exports = 'ONLY IN TRANSACTION';\n",
            encoding="utf-8",
        )

        assert (
            tmp_path / "node_modules" / "prisma" / "index.js"
        ).read_text(
            encoding="utf-8",
        ) == "module.exports = 'prisma';\n"
