"""Append a section to an agent's human input file.

Shared by the web interface (answers, requested changes) and the
automatic diagnosis, so both write instructions the same way and the agent
reads them through the same channel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_factory.context_builder import load_agent_input
from ai_factory.project import get_product_input_path


def agent_input_path(root: Path, config: dict[str, Any], agent_name: str) -> Path:
    product_input = get_product_input_path(root, config)

    if agent_name == "product":
        return product_input

    return product_input.with_name(f"{agent_name}.md")


def append_agent_input(
    root: Path,
    config: dict[str, Any],
    agent_name: str,
    heading: str,
    lines: list[str],
) -> None:
    existing = load_agent_input(root, config, agent_name) or ""
    path = agent_input_path(root, config, agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        existing.rstrip()
        + ("\n\n" if existing.strip() else "")
        + f"## {heading}\n\n"
        + "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )
