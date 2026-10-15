from pathlib import Path
import re
from typing import Any


DEFAULT_WORKSPACE_CONTEXT_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
)

_WORKSPACE_PATH_PATTERN = re.compile(
    r"(?<![\w./\\-])"
    r"((?:src|tests|test|app|lib)/"
    r"[A-Za-z0-9_.\-/]+"
    r"\.[A-Za-z0-9]+)"
)


def get_default_workspace_context_paths(
    project_root: Path,
) -> list[str]:
    return [
        path
        for path in DEFAULT_WORKSPACE_CONTEXT_FILES
        if (project_root / path).is_file()
    ]


def extract_workspace_paths_from_test_results(
    test_results: list[dict[str, Any]],
) -> list[str]:
    """Extract project-relative file paths mentioned by test diagnostics."""

    paths: list[str] = []

    for result in test_results:
        if not isinstance(result, dict):
            continue

        for key in (
            "stdout",
            "stderr",
        ):
            value = result.get(
                key,
                "",
            )

            if not isinstance(value, str):
                continue

            normalized = value.replace(
                "\\",
                "/",
            )

            for match in _WORKSPACE_PATH_PATTERN.finditer(
                normalized
            ):
                path = match.group(1)

                if path not in paths:
                    paths.append(
                        path
                    )

    return paths


_WORD_PATTERN = re.compile(r"[a-z0-9]+")

_CAMEL_BOUNDARY_PATTERN = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])"
)

# Vocabulary of the Factory itself, not of any product it builds. These
# segments appear in task identifiers as structural labels and carry no
# discriminating power.
ENGINE_TASK_ID_STOPWORDS = frozenset(
    {
        "dev",
        "task",
    }
)


def normalize_project_identity(
    project_name: str | None,
) -> tuple[str, ...]:
    """Return the ordered identity words of a project.

    A two-word project name normalizes identically whether it is written in
    camel case, spaced, hyphenated or upper-snake case. The engine never
    stores a project name of its own; the identity is always derived from the
    project under construction.
    """

    if not isinstance(project_name, str) or not project_name.strip():
        return ()

    spaced = _CAMEL_BOUNDARY_PATTERN.sub(
        " ",
        project_name,
    )

    return tuple(
        _WORD_PATTERN.findall(
            spaced.lower()
        )
    )


def resolve_project_identity(
    context: dict[str, Any],
) -> tuple[str, ...]:
    """Resolve the project identity from an already-built agent context.

    Reads the workflow state first, then the project configuration. This
    never touches the filesystem: the caller already holds the loaded
    context.
    """

    if not isinstance(context, dict):
        return ()

    candidates: list[Any] = []

    state = context.get("state")

    if isinstance(state, dict):
        project = state.get("project")

        if isinstance(project, dict):
            candidates.extend(
                [
                    project.get("name"),
                    project.get("id"),
                ]
            )

    project_config = context.get("project")

    if isinstance(project_config, dict):
        project = project_config.get("project")

        if isinstance(project, dict):
            candidates.append(
                project.get("name")
            )

    for candidate in candidates:
        identity = normalize_project_identity(
            candidate
        )

        if identity:
            return identity

    return ()


def _split_words(
    value: str,
) -> list[str]:
    return _WORD_PATTERN.findall(
        value.lower()
    )


def _strip_project_identity(
    tokens: list[str],
    project_identity: tuple[str, ...],
) -> list[str]:
    """Remove the project identity from a task identifier token list.

    The identity is removed as a whole: either as a single collapsed token
    or as a consecutive run of its words. A project word that also names a
    real feature therefore survives when it appears on its own.
    """

    if not project_identity:
        return tokens

    collapsed = "".join(project_identity)

    remaining = [
        token
        for token in tokens
        if token != collapsed
    ]

    if len(project_identity) < 2:
        return remaining

    stripped: list[str] = []
    index = 0

    while index < len(remaining):
        window = tuple(
            remaining[index:index + len(project_identity)]
        )

        if window == project_identity:
            index += len(project_identity)
            continue

        stripped.append(
            remaining[index]
        )
        index += 1

    return stripped


def build_task_relevance_tokens(
    task_id: str,
    *,
    project_identity: tuple[str, ...] = (),
) -> set[str]:
    """Return the discriminating identity tokens of a task."""

    tokens = _strip_project_identity(
        _split_words(task_id),
        project_identity,
    )

    return {
        token
        for token in tokens
        if token not in ENGINE_TASK_ID_STOPWORDS
    }


def _count_matching_tokens(
    path: str,
    task_tokens: set[str],
) -> int:
    """Count task tokens matching a whole word of the path.

    Whole-word matching keeps a directory named after the project from
    matching a feature token that is merely a substring of it.
    """

    path_words = set(
        _split_words(path)
    )

    return sum(
        token in path_words
        or f"{token}s" in path_words
        or token.rstrip("s") in path_words
        for token in task_tokens
    )


def prioritize_diagnostic_paths(
    paths: list[str],
    *,
    task_id: str,
    project_identity: tuple[str, ...] = (),
    limit: int = 8,
) -> list[str]:
    """Prioritize task-relevant diagnostic paths within a fixed bound."""

    unique_paths = list(dict.fromkeys(paths))

    task_tokens = build_task_relevance_tokens(
        task_id,
        project_identity=project_identity,
    )

    def score(path: str) -> tuple[int, str]:
        return (
            -_count_matching_tokens(
                path,
                task_tokens,
            ),
            path.lower(),
        )

    return sorted(
        unique_paths,
        key=score,
    )[:limit]


def is_diagnostic_path_relevant_to_task(
    path: str,
    *,
    task_id: str,
    project_identity: tuple[str, ...] = (),
) -> bool:
    """Return whether a diagnostic path is relevant to a task identity."""

    task_tokens = build_task_relevance_tokens(
        task_id,
        project_identity=project_identity,
    )

    return (
        _count_matching_tokens(
            path,
            task_tokens,
        )
        > 0
    )


_IMPORT_PATTERN = re.compile(
    r"""(?:import|export)\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""
)

_SCRIPT_EXTENSIONS = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
)


def _resolve_local_import(
    project_root: Path,
    importer: Path,
    specifier: str,
) -> Path | None:
    """Resolve a local TypeScript/JavaScript import inside the workspace."""

    if specifier.startswith("@/"):
        base = project_root / "src" / specifier[2:]
    elif specifier.startswith("./") or specifier.startswith("../"):
        base = importer.parent / specifier
    else:
        return None

    candidates: list[Path] = []

    if base.suffix:
        candidates.append(base)
    else:
        candidates.extend(
            base.with_suffix(extension)
            for extension in _SCRIPT_EXTENSIONS
        )
        candidates.extend(
            base / f"index{extension}"
            for extension in _SCRIPT_EXTENSIONS
        )

    root = project_root.resolve()

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except ValueError:
            continue

        if resolved.is_file():
            return resolved

    return None


def expand_workspace_paths_with_local_imports(
    project_root: Path,
    file_paths: list[str],
    *,
    max_dependencies: int = 12,
) -> list[str]:
    """Expand workspace paths with bounded local import dependencies."""

    root = project_root.resolve()
    paths = list(dict.fromkeys(file_paths))
    queue = list(paths)

    dependency_count = 0

    while queue and dependency_count < max_dependencies:
        relative_path = queue.pop(0)
        candidate = project_root / relative_path

        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except ValueError:
            continue

        if not resolved.is_file():
            continue

        if resolved.suffix not in _SCRIPT_EXTENSIONS:
            continue

        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for match in _IMPORT_PATTERN.finditer(content):
            imported = _resolve_local_import(
                project_root,
                resolved,
                match.group(1),
            )

            if imported is None:
                continue

            imported_relative = imported.relative_to(root).as_posix()

            if imported_relative in paths:
                continue

            paths.append(imported_relative)
            queue.append(imported_relative)
            dependency_count += 1

            if dependency_count >= max_dependencies:
                break

    return paths


def build_workspace_snapshot(
    project_root: Path,
    file_paths: list[str],
) -> dict[str, str]:
    """Read existing workspace files for implementation context."""

    snapshot: dict[str, str] = {}

    for relative_path in dict.fromkeys(file_paths):
        candidate = project_root / relative_path

        try:
            resolved = candidate.resolve()
            resolved.relative_to(project_root.resolve())
        except ValueError:
            continue

        if not resolved.is_file():
            continue

        try:
            snapshot[relative_path] = resolved.read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError):
            continue

    return snapshot
