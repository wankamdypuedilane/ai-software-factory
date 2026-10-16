"""Automatic diagnosis of a Developer that stopped converging.

When the Developer repeats the same failure, the guard stops the run
before another blind attempt. On a real project every such stop then
needed an expert: read the test output and the real files, find the cause
(a wrong import, a guessed helper API, a test calling a function with the
wrong signature, a test written without its code), and write a precise
instruction. A person who does not code cannot do that.

This module does it. It gathers the evidence of the failed attempt, asks
the model for the root cause and one precise instruction, appends that
instruction to the Developer input exactly like a human "request changes",
and reopens the budget. It is bounded: at most MAX_AUTO_DIAGNOSES_PER_TASK
per failing task. When the cause needs a human (a credential, a product
decision, an environment the agent cannot fix), it says so in plain words
and the run stops for the human.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_factory.agent_inputs import append_agent_input
from ai_factory.context_builder import load_agent_input
from ai_factory.export_index import build_export_index
from ai_factory.replan_guard import (
    RESETTABLE_STATUSES,
    is_budget_exhausted,
    reset_replan_budget,
)
from ai_factory.retry_evidence import resolve_failed_attempt_evidence
from ai_factory.state import load_state, save_state
from ai_factory.test_references import _LITERAL, _PATH_SHAPE, _candidates


MAX_AUTO_DIAGNOSES_PER_TASK = 2
# A Developer may rename a task when it replans (RS-MVP-010 became
# RS-MVP-010A in a real run), so a per-task bound alone could be renewed
# indefinitely. This one counts every automatic diagnosis since the last
# action of a human, whatever the task.
MAX_AUTO_DIAGNOSES_WITHOUT_HUMAN = 4
HISTORY_FIELD = "auto_diagnoses"
AUTO_HEADING = "Requested changes"
AUTO_MARKER = "(Diagnostic automatique de la Factory)"

MAX_TEST_OUTPUT_CHARS = 6000
MAX_FILE_CHARS = 8000
MAX_FILES_TOTAL_CHARS = 60000
CODE_DIRECTORIES = ("src", "app", "lib", "tests", "test", "scripts", "db", "config")
SKIPPED_PARTS = {"node_modules", ".git", ".factory", ".next", "dist", "build", "__pycache__"}
CODE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py")


@dataclass
class Diagnosis:
    cause: str
    instruction: str
    needs_human: bool = False
    question: str = ""


def diagnosis_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["cause", "instruction", "needs_human", "question"],
        "properties": {
            "cause": {"type": "string"},
            "instruction": {"type": "string"},
            "needs_human": {"type": "boolean"},
            "question": {"type": "string"},
        },
    }


def coerce_diagnosis(value: Any) -> Diagnosis | None:
    if isinstance(value, Diagnosis):
        return value

    if not isinstance(value, dict):
        return None

    cause = str(value.get("cause") or "").strip()
    instruction = str(value.get("instruction") or "").strip()
    needs_human = bool(value.get("needs_human"))
    question = str(value.get("question") or "").strip()

    if not cause or (not needs_human and not instruction):
        return None

    return Diagnosis(cause, instruction, needs_human, question)


# -- evidence -----------------------------------------------------------------


def _head_and_tail(text: str, limit: int) -> str:
    text = text.strip()

    if len(text) <= limit:
        return text

    head = int(limit * 0.4)
    tail = limit - head
    return f"{text[:head]}\n[… {len(text) - limit} characters omitted …]\n{text[-tail:]}"


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _project_code(project_root: Path) -> dict[str, str]:
    files: dict[str, str] = {}

    for directory in CODE_DIRECTORIES:
        base = project_root / directory

        if not base.is_dir():
            continue

        for path in sorted(base.rglob("*")):
            relative = path.relative_to(project_root)

            if SKIPPED_PARTS.intersection(relative.parts) or not path.is_file():
                continue

            if path.suffix in CODE_SUFFIXES:
                content = _read(path)

                if content is not None:
                    files[relative.as_posix()] = content

    return files


def _referenced_paths(project_root: Path, files: dict[str, str]) -> list[str]:
    """Existing project files that the given files read or import."""

    found: list[str] = []

    for path, content in files.items():
        for literal in _LITERAL.findall(content):
            if not _PATH_SHAPE.match(literal):
                continue

            for option in _candidates(path, literal):
                candidates = [option]

                if not Path(option).suffix:
                    candidates += [option + suffix for suffix in CODE_SUFFIXES]

                for candidate in candidates:
                    if (project_root / candidate).is_file() and candidate not in found:
                        found.append(candidate)

    return found


_OUTPUT_PATH = re.compile(r"((?:src|tests|test|app|lib|scripts|db)/[A-Za-z0-9_.\-/\[\]()]+\.[A-Za-z0-9]+)")
SOURCE_FOR_COMPILED = (".ts", ".tsx", ".mts", ".js", ".jsx")


def _paths_in_output(project_root: Path, outputs: list[str]) -> list[str]:
    """Project files named by test output, stack traces included.

    Tests import TypeScript through a transpiled copy, so a stack trace
    names `.test-modules-XYZ/src/server/route.mjs` for `src/server/route.ts`;
    a real diagnosis needed exactly that file.
    """

    found: list[str] = []

    for output in outputs:
        for match in _OUTPUT_PATH.finditer(output.replace("\\\\", "/").replace("\\", "/")):
            path = match.group(1)
            options = [path]
            stem, _, suffix = path.rpartition(".")

            if suffix in {"mjs", "js", "cjs"}:
                options += [f"{stem}{extension}" for extension in SOURCE_FOR_COMPILED]

            for option in options:
                if (project_root / option).is_file() and option not in found:
                    found.append(option)
                    break

    return found


def _developer(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("agents", {}).get("developer", {}) or {}


def _failed_task(last_result: dict[str, Any]) -> tuple[str, str]:
    task_id = str(last_result.get("failed_task_id") or "")

    for request in last_result.get("implementation_requests", []) or []:
        if isinstance(request, dict) and request.get("id") == task_id:
            return task_id, f"{request.get('title', '')}: {request.get('purpose', '')}"

    return task_id, ""


def build_diagnosis_prompt(
    project_root: Path,
    state: dict[str, Any],
    developer_input: str,
) -> str:
    last_result = _developer(state).get("last_result", {}) or {}
    task_id, task_text = _failed_task(last_result)
    test_results = last_result.get("test_results", []) or []

    sections = [
        "# Diagnose A Developer That Stopped Converging",
        "",
        "You are the senior engineer of an AI software factory. The Developer "
        "agent produced the same failure twice in a row and was stopped. Find "
        "the root cause from the evidence below and write ONE precise "
        "instruction that lets the Developer fix it on its next attempt.",
        "",
        "## Failing Task",
        f"{task_id} {task_text}".strip() or "(unknown task)",
        "",
        f"Failure signature: {last_result.get('failure_signature', '')}",
    ]

    blockers = last_result.get("implementation_blockers", []) or []

    if blockers:
        sections.extend(["", "## Blockers Reported By The Developer", repr(blockers)])

    failing = [result for result in test_results if isinstance(result, dict) and result.get("returncode")]

    if failing:
        sections.extend(["", "## Failing Test Output"])

        for result in failing:
            sections.extend(
                [
                    "",
                    f"Command: {result.get('command', '')}",
                    _head_and_tail(str(result.get("stdout", "")), MAX_TEST_OUTPUT_CHARS),
                    _head_and_tail(str(result.get("stderr", "")), MAX_TEST_OUTPUT_CHARS // 3),
                ]
            )

    evidence = resolve_failed_attempt_evidence(project_root, state, task_id) if task_id else None
    attempt_files = dict(evidence.authored_files) if evidence else {}

    if attempt_files:
        sections.extend(
            [
                "",
                "## Files Written By The Failed Attempt (rolled back, not in the project)",
            ]
        )

        for path, content in attempt_files.items():
            sections.extend(["", f"### {path}", _head_and_tail(content, MAX_FILE_CHARS)])

    project_code = _project_code(project_root)
    related = _referenced_paths(project_root, attempt_files)

    outputs = [str(result.get(key, "")) for result in failing for key in ("stdout", "stderr")]

    for path in _paths_in_output(project_root, outputs):
        if path not in related:
            related.append(path)

    # One level further: what those files themselves use.
    for path in _referenced_paths(
        project_root,
        {path: project_code.get(path) or _read(project_root / path) or "" for path in related},
    ):
        if path not in related:
            related.append(path)

    if related:
        sections.extend(["", "## Existing Project Files They Use (the source of truth)"])
        used = 0

        for path in related:
            content = project_code.get(path) or _read(project_root / path) or ""
            block = _head_and_tail(content, MAX_FILE_CHARS)

            if used + len(block) > MAX_FILES_TOTAL_CHARS:
                sections.append(f"\n[further files omitted: {', '.join(related[related.index(path):])}]")
                break

            sections.extend(["", f"### {path}", block])
            used += len(block)

    index = build_export_index(project_code)

    if index:
        sections.extend(["", "## Export Index Of The Whole Project", *index])

    if developer_input.strip():
        sections.extend(
            [
                "",
                "## Instructions Already Given To The Developer",
                _head_and_tail(developer_input, 8000),
            ]
        )

    sections.extend(
        [
            "",
            "## How To Answer",
            "- cause: the root cause in one or two sentences, in French, "
            "understandable by someone who does not code.",
            "- instruction: in French, addressed to the Developer. Name the "
            "exact files, functions, signatures and values, quoting the "
            "existing project files above as the source of truth. Say what "
            "to change and what to keep. When a test contradicts working "
            "existing code, fix the test, not the code. When code is missing, "
            "say which file to write. End with: continue all remaining MVP "
            "tasks.",
            "- Do not repeat an instruction already given above unless you "
            "explain why it was not applied and how to apply it.",
            "- needs_human: true ONLY when no code change can fix it: a "
            "missing credential or paid service, an unreachable database or "
            "tool the agent cannot install, or a product decision only the "
            "owner can take. Then question: one short question in plain "
            "French for a person who does not code, and instruction may be "
            "empty. Otherwise needs_human is false and question is empty.",
        ]
    )

    return "\n".join(sections)


# -- the step -----------------------------------------------------------------


def _attempts_for(developer: dict[str, Any], task_id: str) -> int:
    return sum(
        1
        for entry in developer.get(HISTORY_FIELD, []) or []
        if isinstance(entry, dict) and entry.get("task_id") == task_id
    )


def _attempts_since_human(developer: dict[str, Any]) -> int:
    human_resets = [
        str(entry.get("at", ""))
        for entry in developer.get("replan_budget_resets", []) or []
        if isinstance(entry, dict) and not str(entry.get("source", "")).startswith("auto:")
    ]
    since = max(human_resets, default="")

    return sum(
        1
        for entry in developer.get(HISTORY_FIELD, []) or []
        if isinstance(entry, dict) and str(entry.get("at", "")) > since
    )


def has_diagnosis_left(state: dict[str, Any]) -> bool:
    """Whether a stopped Developer may still be diagnosed automatically."""

    developer = _developer(state)
    last_result = developer.get("last_result", {}) or {}
    task_id = str(last_result.get("failed_task_id") or last_result.get("failure_signature") or "")

    return (
        developer.get("status") in RESETTABLE_STATUSES
        and is_budget_exhausted(state, "developer")
        and bool(task_id)
        and _attempts_for(developer, task_id) < MAX_AUTO_DIAGNOSES_PER_TASK
        and _attempts_since_human(developer) < MAX_AUTO_DIAGNOSES_WITHOUT_HUMAN
    )


def can_auto_diagnose(state: dict[str, Any], provider: Any) -> bool:
    return callable(getattr(provider, "diagnose", None)) and has_diagnosis_left(state)


def try_auto_diagnosis(project_root: Path, provider: Any) -> bool:
    """Diagnose the stopped Developer; return True when it may run again."""

    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)

    if not can_auto_diagnose(state, provider):
        return False

    config = load_state(project_root / ".factory" / "project.yaml")
    developer = _developer(state)
    last_result = developer.get("last_result", {}) or {}
    task_id = str(last_result.get("failed_task_id") or last_result.get("failure_signature"))

    developer_input = load_agent_input(project_root, config, "developer") or ""
    diagnosis = coerce_diagnosis(
        provider.diagnose(build_diagnosis_prompt(project_root, state, developer_input))
    )

    if diagnosis is None:
        return False

    developer.setdefault(HISTORY_FIELD, []).append(
        {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "task_id": task_id,
            "failure_signature": last_result.get("failure_signature", ""),
            "cause": diagnosis.cause,
            "instruction": diagnosis.instruction,
            "needs_human": diagnosis.needs_human,
            "question": diagnosis.question,
        }
    )

    if diagnosis.needs_human:
        save_state(state_path, state)
        return False

    append_agent_input(
        project_root,
        config,
        "developer",
        AUTO_HEADING,
        [AUTO_MARKER, "", diagnosis.instruction],
    )
    reset_replan_budget(state, "developer", source="auto:diagnosis")
    save_state(state_path, state)

    return True


def latest_diagnosis(state: dict[str, Any]) -> dict[str, Any] | None:
    history = _developer(state).get(HISTORY_FIELD, []) or []
    return history[-1] if history and isinstance(history[-1], dict) else None
