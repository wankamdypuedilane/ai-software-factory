"""Isolated execution of one implementation unit.

A unit runs against a private copy of the project. Its changes reach the real
workspace only after every declared validation passed, and only as the
precise set of files the unit actually changed.
"""

from dataclasses import dataclass, field
import hashlib
import os
import shutil
import time
import sys
import tempfile
from pathlib import Path


class PromotionConflictError(RuntimeError):
    """Raised when the real workspace changed under a promoted file."""


# Derived, vendored or Factory-owned directories. None of them is source of
# truth for a project, and copying them would dominate the cost of a task.
DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".factory",
        ".hg",
        ".svn",
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
        "node_modules",
    }
)

# Vendored dependencies are expensive to copy. They may be shared with the
# transaction only while no declared command can write into them.
SHAREABLE_DEPENDENCY_DIRECTORIES = (
    "node_modules",
)

FAILED_TRANSACTION_DIRECTORY = (
    ".factory/failed-transactions"
)


def _hash_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _iter_files(
    root: Path,
    excluded_directories: frozenset[str],
) -> list[Path]:
    files: list[Path] = []

    for current, directories, filenames in os.walk(root):
        directories[:] = [
            name
            for name in directories
            if name not in excluded_directories
        ]

        current_path = Path(current)

        for filename in filenames:
            files.append(
                current_path / filename
            )

    return files


def _build_manifest(
    root: Path,
    excluded_directories: frozenset[str],
) -> dict[str, str]:
    """Map every relevant file to a content digest."""

    manifest: dict[str, str] = {}

    if not root.is_dir():
        return manifest

    for path in _iter_files(
        root,
        excluded_directories,
    ):
        try:
            digest = _hash_file(path)
        except OSError:
            continue

        relative = (
            path.relative_to(root)
            .as_posix()
        )

        manifest[relative] = digest

    return manifest


# Commands that build the dependency directory themselves. A unit declaring
# one of them starts from an empty directory; any other unit needs the
# dependencies the workspace already validated.
DEPENDENCY_INSTALL_COMMANDS = frozenset(
    {
        "npm install --ignore-scripts",
        "npm ci --ignore-scripts",
    }
)


def requires_dependency_seed(
    setup_commands: list[str] | None,
) -> bool:
    """Return whether an isolated transaction must be given the dependencies.

    A unit that installs its own dependencies does not need them copied. Any
    other unit does: an isolated but empty directory would leave commands
    such as a client generator without the binaries they invoke.
    """

    declared = [
        command.strip()
        for command in (setup_commands or [])
        if isinstance(command, str) and command.strip()
    ]

    if not declared:
        return False

    return not any(
        command in DEPENDENCY_INSTALL_COMMANDS
        for command in declared
    )


def mutates_shared_dependencies(
    setup_commands: list[str],
) -> bool:
    """Return whether a declared command may write into dependencies.

    Every setup command the Factory allows installs packages or generates a
    client inside the dependency directory, so declaring any of them forces
    full isolation.
    """

    return bool(
        [
            command
            for command in setup_commands
            if isinstance(command, str) and command.strip()
        ]
    )


def _link_directory(
    source: Path,
    target: Path,
) -> bool:
    """Link a directory into the transaction without copying it."""

    if sys.platform == "win32":
        try:
            import _winapi

            _winapi.CreateJunction(
                str(source),
                str(target),
            )

            return True
        except (OSError, ImportError, AttributeError):
            return False

    try:
        os.symlink(
            source,
            target,
            target_is_directory=True,
        )

        return True
    except OSError:
        return False


@dataclass
class WorkspaceTransaction:
    """A private copy of the workspace for one implementation unit."""

    source_root: Path
    root: Path
    excluded_directories: frozenset[str]
    shared_directories: tuple[str, ...] = ()
    isolated_dependencies: tuple[str, ...] = ()
    source_manifest: dict[str, str] = field(
        default_factory=dict
    )
    baseline_manifest: dict[str, str] = field(
        default_factory=dict
    )
    promoted: bool = False

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "WorkspaceTransaction":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.discard()

    def discard(self) -> None:
        """Delete the transaction. The real workspace is never touched."""

        if not self.root.exists():
            return

        # Detach every shared directory FIRST. A junction left in place
        # could otherwise be followed while deleting the transaction, which
        # would destroy the real dependencies.
        for name in self.shared_directories:
            linked = self.root / name

            if not linked.exists():
                continue

            try:
                linked.rmdir()
            except OSError:
                try:
                    os.unlink(linked)
                except OSError:
                    # Refuse to delete the transaction while a link into
                    # the real workspace is still attached.
                    return

        shutil.rmtree(
            self.root,
            ignore_errors=True,
        )

    # -- inspection --------------------------------------------------------

    def _current_manifest(self) -> dict[str, str]:
        return _build_manifest(
            self.root,
            self._walk_exclusions(),
        )

    def _walk_exclusions(self) -> frozenset[str]:
        return self.excluded_directories | set(
            self.shared_directories
        )

    def changed_paths(self) -> list[str]:
        """Return the files this transaction created or modified."""

        current = self._current_manifest()

        return sorted(
            relative
            for relative, digest in current.items()
            if self.baseline_manifest.get(relative) != digest
        )

    def changed_files(self) -> dict[str, str]:
        """Return the changed files with their transaction content."""

        contents: dict[str, str] = {}

        for relative in self.changed_paths():
            path = self.root / relative

            try:
                contents[relative] = path.read_text(
                    encoding="utf-8",
                )
            except (OSError, UnicodeDecodeError):
                continue

        return contents

    # -- promotion ---------------------------------------------------------

    def promote(self) -> list[str]:
        """Apply the transaction changes to the real workspace.

        Verifies first, writes second: a workspace file that changed under
        the transaction aborts the whole promotion instead of being
        silently overwritten.
        """

        changed = self.changed_paths()

        conflicts = [
            relative
            for relative in changed
            if self._has_conflict(relative)
        ]

        if conflicts:
            raise PromotionConflictError(
                "The workspace changed under this task; "
                "nothing was promoted: "
                + ", ".join(conflicts)
            )

        for relative in changed:
            target = self.source_root / relative

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copyfile(
                self.root / relative,
                target,
            )

        for name in self.isolated_dependencies:
            self._promote_dependency_directory(name)

        self.promoted = True

        return changed

    def _promote_dependency_directory(
        self,
        name: str,
    ) -> None:
        """Move an isolated dependency directory into the workspace.

        A unit that declared a setup command installed its dependencies
        inside the transaction. Leaving the workspace with the previous
        dependencies would break the next unit, so the derived directory is
        replaced as a whole once the unit passed.
        """

        source = self.root / name

        if not source.is_dir():
            return

        target = self.source_root / name
        previous = self.source_root / f"{name}.ai-factory-previous"

        if previous.exists():
            shutil.rmtree(
                previous,
                ignore_errors=True,
            )

        if target.exists() and not _rename_with_retries(target, previous):
            # Windows refuses to rename a directory while any file in it is
            # open (antivirus, indexer, a node process). A real run stopped
            # on "[WinError 5] Access denied" here. The installed files are
            # copied over the existing directory instead: the unit already
            # passed its tests with them.
            _copy_over(source, target)
            return

        try:
            shutil.move(
                str(source),
                str(target),
            )
        except OSError:
            if previous.exists() and not target.exists():
                previous.rename(target)

            raise

        shutil.rmtree(
            previous,
            ignore_errors=True,
        )

    def _has_conflict(
        self,
        relative: str,
    ) -> bool:
        target = self.source_root / relative

        expected = self.source_manifest.get(relative)

        if not target.is_file():
            return expected is not None

        try:
            return _hash_file(target) != expected
        except OSError:
            return True


RENAME_ATTEMPTS = 5
RENAME_DELAY_SECONDS = 1.0


def _rename_with_retries(source: Path, target: Path) -> bool:
    """Rename, retrying while Windows holds a transient lock."""

    for attempt in range(RENAME_ATTEMPTS):
        try:
            source.rename(target)
            return True
        except PermissionError:
            if attempt + 1 < RENAME_ATTEMPTS:
                time.sleep(RENAME_DELAY_SECONDS)
        except OSError:
            return False

    return False


def _copy_over(source: Path, target: Path) -> None:
    """Copy every file of `source` into `target`, skipping locked files."""

    for directory, _dirnames, filenames in os.walk(source):
        relative = Path(directory).relative_to(source)
        destination = target / relative

        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue

        for name in filenames:
            try:
                shutil.copy2(Path(directory) / name, destination / name)
            except OSError:
                continue


def open_workspace_transaction(
    source_root: Path,
    setup_commands: list[str] | None = None,
    excluded_directories: frozenset[str] | None = None,
) -> WorkspaceTransaction:
    """Open an isolated transaction over a project workspace."""

    exclusions = (
        excluded_directories
        if excluded_directories is not None
        else DEFAULT_EXCLUDED_DIRECTORIES
    )

    source_root = Path(source_root)

    # Resolved so that a short or symlinked temp path cannot break the
    # translation of transaction paths back to workspace paths.
    transaction_root = (
        Path(
            tempfile.mkdtemp(
                prefix="ai-factory-tx-",
            )
        ).resolve()
        / "workspace"
    )

    shutil.copytree(
        source_root,
        transaction_root,
        ignore=shutil.ignore_patterns(
            *exclusions
        ),
        symlinks=True,
    )

    shared: list[str] = []
    isolated: list[str] = []

    dependencies_are_mutated = mutates_shared_dependencies(
        setup_commands or []
    )

    seed_dependencies = requires_dependency_seed(
        setup_commands or []
    )

    for name in SHAREABLE_DEPENDENCY_DIRECTORIES:
        if dependencies_are_mutated:
            # A declared setup command writes into this directory, so the
            # transaction must own its own copy rather than share one.
            isolated.append(name)

            candidate = source_root / name

            if seed_dependencies and candidate.is_dir():
                # Seeded as a real copy, never a link: the setup command
                # must be free to mutate it without any of that reaching
                # the real workspace.
                shutil.copytree(
                    candidate,
                    transaction_root / name,
                    symlinks=True,
                    copy_function=shutil.copyfile,
                    dirs_exist_ok=True,
                )

            continue

        candidate = source_root / name

        if not candidate.is_dir():
            continue

        if _link_directory(
            candidate,
            transaction_root / name,
        ):
            shared.append(name)

    walk_exclusions = exclusions | set(shared)

    baseline_manifest = _build_manifest(
        transaction_root,
        walk_exclusions,
    )

    source_manifest = _build_manifest(
        source_root,
        walk_exclusions,
    )

    return WorkspaceTransaction(
        source_root=source_root,
        root=transaction_root,
        excluded_directories=exclusions,
        shared_directories=tuple(shared),
        isolated_dependencies=tuple(isolated),
        source_manifest=source_manifest,
        baseline_manifest=baseline_manifest,
    )


# --------------------------------------------------------------------------
# Failed attempt diagnostics
#
# Rolling the workspace back must not cost the retry its context. The files a
# failed unit produced are kept as Factory metadata, outside the project tree.
# --------------------------------------------------------------------------


def failed_transaction_directory_name(
    task_id: str,
) -> str:
    """Return the on-disk directory name for a task's diagnostics.

    Exposed so that anything storing the same evidence elsewhere - a
    checkpoint, for instance - agrees with the runtime on where it lives.
    """

    return "".join(
        character
        if character.isalnum() or character in {"-", "_", "."}
        else "_"
        for character in task_id
    ) or "task"


def _failed_transaction_root(
    project_root: Path,
    task_id: str,
) -> Path:
    return (
        project_root
        / FAILED_TRANSACTION_DIRECTORY
        / failed_transaction_directory_name(task_id)
    )


GENERATED_ARTIFACTS_MANIFEST = "generated-artifacts.txt"

AUTHORED_FILES_DIRECTORY = "files"


def save_failed_transaction_snapshot(
    project_root: Path,
    task_id: str,
    files: dict[str, str],
    generated_paths: list[str] | tuple[str, ...] = (),
) -> Path:
    """Persist what a failed unit produced, outside the project tree.

    Only files the agent authored are kept with their content. Artifacts a
    setup command produced - lockfiles, generated clients, build outputs -
    are recorded by name alone: their content is derived, unbounded, and
    useless for repairing the attempt.
    """

    root = _failed_transaction_root(
        project_root,
        task_id,
    )

    if root.exists():
        shutil.rmtree(
            root,
            ignore_errors=True,
        )

    authored_root = root / AUTHORED_FILES_DIRECTORY

    for relative, content in files.items():
        target = authored_root / relative

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_text(
            content,
            encoding="utf-8",
        )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    (root / GENERATED_ARTIFACTS_MANIFEST).write_text(
        "\n".join(
            sorted(generated_paths)
        ),
        encoding="utf-8",
    )

    return root


def load_failed_transaction_snapshot(
    project_root: Path,
    task_id: str,
) -> dict[str, str]:
    """Return the agent-authored files of the last failed attempt."""

    root = (
        _failed_transaction_root(
            project_root,
            task_id,
        )
        / AUTHORED_FILES_DIRECTORY
    )

    if not root.is_dir():
        return {}

    snapshot: dict[str, str] = {}

    for path in _iter_files(
        root,
        frozenset(),
    ):
        try:
            snapshot[
                path.relative_to(root).as_posix()
            ] = path.read_text(
                encoding="utf-8",
            )
        except (OSError, UnicodeDecodeError):
            continue

    return snapshot


def load_failed_transaction_generated_paths(
    project_root: Path,
    task_id: str,
) -> list[str]:
    """Return the setup-generated artifact paths of the last failed attempt."""

    manifest = (
        _failed_transaction_root(
            project_root,
            task_id,
        )
        / GENERATED_ARTIFACTS_MANIFEST
    )

    if not manifest.is_file():
        return []

    try:
        content = manifest.read_text(
            encoding="utf-8",
        )
    except OSError:
        return []

    return [
        line.strip()
        for line in content.splitlines()
        if line.strip()
    ]
