"""Narrow, Factory-owned permission to run a package's own build step.

Dependencies are installed with lifecycle scripts disabled, which refuses
arbitrary code execution from every package in a transitive tree. Some
packages obtain a compiled artifact through exactly that lifecycle, so the
policy that keeps the install safe also leaves those packages installed and
permanently unusable - and the failure then looks like a defect in generated
product code, which no rewrite of that code could ever repair.

The permission that resolves this is a name, not a switch: a project may
declare which packages are allowed to run their own build step, and the
Factory derives a command scoped to those names alone. The declaration lives
in the project configuration, which only `init` and the human-approved
technology command ever write, so an agent has no path to it. The agent-facing
command allowlist never contains the derived command at all: the model cannot
propose it, in a response or in prose.
"""

import json
import re
from pathlib import Path
from typing import Any

from ai_factory.state import load_state


NATIVE_PREPARATION_PREFIX = "npm rebuild "

# The artifact a node native addon loads at runtime. Its absence is what
# makes an installed package unusable, whatever the package is called.
NATIVE_ARTIFACT_SUFFIX = ".node"

# The lifecycle hooks that build or fetch that artifact.
LIFECYCLE_SCRIPT_NAMES = (
    "preinstall",
    "install",
    "postinstall",
)

DEPENDENCY_MANIFEST_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
)

# npm package names, optionally scoped. Anything else is refused rather than
# interpreted: the name is interpolated into a command line.
PACKAGE_NAME_PATTERN = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$"
)


def native_preparation_command(
    package: str,
) -> str:
    """Return the preparation command for one approved package."""

    return f"{NATIVE_PREPARATION_PREFIX}{package}"


def is_native_preparation_command(
    command: str,
    approved_native_packages: tuple[str, ...] | list[str] = (),
) -> bool:
    """Return whether a command is the preparation of an approved package.

    Matching is by exact reconstruction, never by parsing the command: a
    command is recognised only if it is character-for-character the one the
    Factory would have produced for a name it approved.
    """

    if not isinstance(command, str):
        return False

    return command.strip() in {
        native_preparation_command(package)
        for package in approved_native_packages
        if isinstance(package, str)
    }


def load_approved_native_packages(
    project_root: Path,
) -> tuple[str, ...]:
    """Return the packages this project may build from lifecycle scripts.

    Fails closed: an absent declaration grants nothing, and a declaration
    the Factory cannot verify is refused rather than partially honoured.
    """

    config_path = (
        Path(project_root)
        / ".factory"
        / "project.yaml"
    )

    if not config_path.is_file():
        return ()

    try:
        config = load_state(config_path)
    except (OSError, ValueError):
        return ()

    dependencies = config.get("dependencies")

    if not isinstance(dependencies, dict):
        return ()

    declared = dependencies.get("native_builds")

    if declared is None:
        return ()

    if not isinstance(declared, (list, tuple)):
        raise ValueError(
            "Project configuration dependencies.native_builds must be a "
            "list of package names."
        )

    approved: list[str] = []

    for entry in declared:
        if (
            not isinstance(entry, str)
            or not PACKAGE_NAME_PATTERN.match(entry.strip())
        ):
            raise ValueError(
                "Project configuration declares an invalid native build "
                f"package name: {entry!r}"
            )

        name = entry.strip()

        if name not in approved:
            approved.append(name)

    return tuple(approved)


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def package_is_declared(
    project_root: Path,
    package: str,
) -> bool:
    """Return whether the project manifest depends on the package.

    An approval is a permission, not an instruction: a package the project
    does not use is never prepared.
    """

    manifest = _read_json(
        Path(project_root) / "package.json"
    )

    for section in DEPENDENCY_MANIFEST_SECTIONS:
        entries = manifest.get(section)

        if isinstance(entries, dict) and package in entries:
            return True

    return False


def package_declares_lifecycle_scripts(
    node_modules: Path,
    package: str,
) -> bool:
    """Return whether the installed package builds itself on install."""

    manifest = _read_json(
        Path(node_modules) / package / "package.json"
    )

    scripts = manifest.get("scripts")

    if not isinstance(scripts, dict):
        return False

    return any(
        isinstance(scripts.get(name), str) and scripts[name].strip()
        for name in LIFECYCLE_SCRIPT_NAMES
    )


def native_artifact_present(
    node_modules: Path,
    package: str,
) -> bool:
    """Return whether the package's compiled artifact is installed."""

    package_root = Path(node_modules) / package

    if not package_root.is_dir():
        return False

    for path in package_root.rglob(f"*{NATIVE_ARTIFACT_SUFFIX}"):
        if path.is_file():
            return True

    return False


def requires_native_preparation(
    project_root: Path,
    package: str,
    fresh_install: bool,
) -> bool:
    """Return whether an approved package must be prepared before use.

    A unit that installs its dependencies from scratch always loses the
    artifact, because that install runs with lifecycle scripts disabled.
    Otherwise the package needs preparation only while it is installed,
    declares a build step, and has no artifact to show for it.
    """

    project_root = Path(project_root)

    if not package_is_declared(project_root, package):
        return False

    node_modules = project_root / "node_modules"

    if fresh_install:
        return True

    if not (node_modules / package).is_dir():
        return False

    if not package_declares_lifecycle_scripts(node_modules, package):
        return False

    return not native_artifact_present(node_modules, package)


def build_native_preparation_commands(
    project_root: Path,
    setup_commands: list[str] | None,
) -> list[str]:
    """Return the preparation commands this unit needs, in declared order.

    The Factory authors these commands. They are never taken from a model
    response, and an empty or absent declaration produces none of them.
    """

    from ai_factory.workspace_transaction import (
        DEPENDENCY_INSTALL_COMMANDS,
    )

    approved = load_approved_native_packages(project_root)

    if not approved:
        return []

    fresh_install = any(
        command.strip() in DEPENDENCY_INSTALL_COMMANDS
        for command in (setup_commands or [])
        if isinstance(command, str)
    )

    return [
        native_preparation_command(package)
        for package in approved
        if requires_native_preparation(
            project_root=project_root,
            package=package,
            fresh_install=fresh_install,
        )
    ]
