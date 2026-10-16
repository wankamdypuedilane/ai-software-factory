"""Files a returned test reads or imports that will not exist.

A real unit wrote tests/ui-foundation.test.mjs, which reads
src/app/layout.tsx and src/app/globals.css, without writing either file.
Every test then failed with ENOENT, twice, and the step stopped. The paths
a test names are visible in its source, so the Factory can check them
before anything is applied and ask for a corrected response instead.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re


TEST_FILE_MARKERS = ("test", "spec")
CODE_SUFFIXES = (
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    ".py", ".css", ".scss", ".json", ".html", ".sql", ".md", ".yaml", ".yml",
)

# Quoted string literals; only those shaped like relative file paths count.
_LITERAL = re.compile(r"""["'`]([^"'`\s${}]+)["'`]""")
_PATH_SHAPE = re.compile(r"^(?:\.{1,2}/)?[A-Za-z0-9_@.\-]+(?:/[A-Za-z0-9_@.\-\[\]()]+)+$")


def _is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return any(marker in name for marker in TEST_FILE_MARKERS)


def _candidates(test_path: str, literal: str) -> list[str]:
    """Where a literal may point: relative to the test, or to the root."""

    test_dir = PurePosixPath(test_path).parent
    options: list[str] = []

    if literal.startswith(("./", "../")):
        options.append(str(PurePosixPath(*_resolve(test_dir / literal))))
        options.append(str(PurePosixPath(*_resolve(PurePosixPath(literal)))))
    else:
        options.append(literal)

    return [option for option in options if option and not option.startswith("..")]


def _resolve(path: PurePosixPath) -> list[str]:
    parts: list[str] = []

    for part in path.parts:
        if part == "..":
            if parts:
                parts.pop()
            else:
                parts.append("..")
        elif part != ".":
            parts.append(part)

    return parts or ["."]


def find_missing_test_references(
    project_root: Path,
    files: dict[str, str],
) -> list[tuple[str, str]]:
    """Return (test file, referenced path) pairs that will not exist.

    `files` maps the paths a response writes to their content. A reference
    is satisfied by a file that exists in the project or in the response,
    or by a directory, so only clear file references are reported.
    """

    written = {path.removeprefix("./") for path in files}
    missing: list[tuple[str, str]] = []

    for test_path, content in files.items():
        if not _is_test_file(test_path):
            continue

        for literal in _LITERAL.findall(content):
            if not _PATH_SHAPE.match(literal):
                continue

            if not literal.lower().endswith(CODE_SUFFIXES):
                continue

            # Package imports such as "node:test" or "@scope/pkg/x.js" are
            # not project files.
            if not literal.startswith((".", "src/", "app/", "tests/", "test/", "lib/",
                                       "config/", "db/", "public/", "scripts/", "docs/")):
                continue

            options = _candidates(test_path, literal)

            if not options:
                continue

            if any(
                option in written or (project_root / option).exists()
                for option in options
            ):
                continue

            pair = (test_path, options[0])

            if pair not in missing:
                missing.append(pair)

    return missing


def build_missing_reference_correction(
    task_id: str,
    missing: list[tuple[str, str]],
) -> list[str]:
    corrections = [
        "The previous response was rejected by the Factory runtime and was not applied.",
        f"Return a corrected response for task {task_id}.",
    ]
    corrections.extend(
        f"{test_path} reads or imports {target}, which does not exist and is "
        "not written by this response."
        for test_path, target in missing
    )
    corrections.extend(
        [
            "Write every file your tests read or import, with its complete "
            "content, in this same response; a test that reads a missing file "
            "always fails.",
            "If a test points at a wrong path, fix the path instead.",
            "Do not report this correction as a blocker.",
        ]
    )
    return corrections
