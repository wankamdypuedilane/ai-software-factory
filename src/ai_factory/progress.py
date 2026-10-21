"""Progress of a long Developer step, written after every unit.

The workflow state is saved when a whole Developer cycle ends. With Claude
Code a cycle ran for hours on a real project while the page only showed a
timer, and nobody could tell whether it was working or stuck. The batch
now records which unit runs, since when, and which ones finished, in
`.factory/progress.json`; the web page shows it while the step runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


PROGRESS_FILE = Path(".factory") / "progress.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProgressRecorder:
    def __init__(self, project_root: Path, agent: str, tasks: list[Any]) -> None:
        self.path = project_root / PROGRESS_FILE
        self.data: dict[str, Any] = {
            "agent": agent,
            "total": len(tasks),
            "tasks": [{"id": task.id, "title": task.title} for task in tasks],
            "done": [],
            "current": None,
            "updated_at": _now(),
        }
        self._write()

    def _write(self) -> None:
        self.data["updated_at"] = _now()

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass  # progress is informative; it never stops the work

    def start(self, index: int, task: Any) -> None:
        self.data["current"] = {
            "index": index + 1,
            "id": task.id,
            "title": task.title,
            "started_at": _now(),
        }
        self._write()

    def finish(self, task: Any, outcome: str) -> None:
        current = self.data.get("current") or {}
        self.data["done"].append(
            {
                "id": task.id,
                "title": task.title,
                "outcome": outcome,
                "started_at": current.get("started_at"),
                "finished_at": _now(),
            }
        )
        self.data["current"] = None
        self._write()


def read_progress(project_root: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((project_root / PROGRESS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    return data if isinstance(data, dict) else None
