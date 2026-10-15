import os
from pathlib import Path


FACTORY_HOME_ENV = "AI_FACTORY_HOME"

_PACKAGE_DIR = Path(__file__).resolve().parent
_PACKAGED_DATA_DIR = _PACKAGE_DIR / "_data"
_SOURCE_CHECKOUT_DIR = _PACKAGE_DIR.parents[1]


def _resolve_resource_dir(name: str) -> Path:
    """Locate a bundled Factory resource directory.

    Lookup order:
    1. ``$AI_FACTORY_HOME/<name>`` when the variable is set.
    2. The copy shipped inside the installed package (``pip install .``).
    3. The repository checkout (``pip install -e .`` / running from source).
    """

    override = os.getenv(FACTORY_HOME_ENV)

    if override:
        candidate = Path(override).expanduser() / name

        if not candidate.is_dir():
            raise FileNotFoundError(
                f"{FACTORY_HOME_ENV} does not contain '{name}': {candidate}"
            )

        return candidate

    for root in (
        _PACKAGED_DATA_DIR,
        _SOURCE_CHECKOUT_DIR,
    ):
        candidate = root / name

        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        f"Factory resource directory not found: {name}. "
        f"Reinstall the package or set {FACTORY_HOME_ENV}."
    )


def get_agents_dir() -> Path:
    """Return the directory containing agent contracts."""

    return _resolve_resource_dir("agents")


def get_templates_dir() -> Path:
    """Return the directory containing project templates."""

    return _resolve_resource_dir("templates")


def get_source_checkout_dir() -> Path:
    """Return the repository root when running from a source checkout."""

    return _SOURCE_CHECKOUT_DIR
