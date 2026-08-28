from pathlib import Path

FACTORY_VERSION = "1.0"

PROJECT_ROOT = Path.cwd()

STATE_DIR = ".factory"
STATE_FILE = "state.yaml"

DEFAULT_AGENTS = [
    "product",
    "ux_ui",
    "architect",
    "developer",
    "qa",
    "security",
    "devops",
    "sre",
]