"""Claude Code as the Factory's model provider.

The OpenAI Developer writes every file of a task in one response, without
seeing it run; the Factory then runs the tests and sends the failure back.
On a real project most of the budget went into that loop. Claude Code reads
the real files, runs the tests, sees the error and fixes it before handing
back, and it runs on the owner's Claude subscription instead of API credit.

Implementation tasks run Claude Code in the project directory with file and
shell tools. The files it changed are collected, the project is restored,
and the changes go through the Factory's usual transaction: applied in an
isolated workspace, validated with the declared tests, committed or rolled
back. Every other call (agent results, documents, reviews, diagnosis) runs
Claude Code without write tools and parses its JSON answer with the same
parsers as the OpenAI provider.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from ai_factory.implementation_result import ImplementationResult
from ai_factory.openai_provider import OpenAIProvider, build_implementation_result_schema
from ai_factory.process_runner import run_process
from ai_factory.project_environment import active_project_environment
from ai_factory.provider_errors import ProviderErrorKind, ProviderExecutionError


DEFAULT_CALL_TIMEOUT_SECONDS = 15 * 60
DEFAULT_IMPLEMENTATION_TIMEOUT_SECONDS = 45 * 60

# Never collected as a change, never restored: dependencies, engine state,
# build output and the transpiled copies tests create.
SKIPPED_DIRECTORIES = {
    "node_modules", ".git", ".factory", ".next", "dist", "build", "coverage",
    "__pycache__", ".venv", "venv", ".pytest_cache", ".turbo", ".cache",
}
SKIPPED_PREFIXES = (".test-modules",)
MAX_COLLECTED_FILE_BYTES = 1_000_000

READ_ONLY_TOOLS = "Read,Glob,Grep"
IMPLEMENTATION_TOOLS = "Bash,Read,Edit,Write,Glob,Grep"

LIMIT_MARKERS = (
    "usage limit", "rate limit", "limit reached", "quota", "overloaded",
    "weekly limit", "daily limit", "session limit", "hit your", "resets ",
)
AUTH_MARKERS = ("not logged in", "please run /login", "invalid api key", "authentication", "oauth")

IMPLEMENTATION_FINAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["task_id", "summary", "setup_commands", "tests", "blockers"],
    "properties": {
        "task_id": {"type": "string"},
        "summary": {"type": "string"},
        "setup_commands": {"type": "array", "items": {"type": "string"}},
        "tests": {"type": "array", "items": {"type": "string"}},
        "blockers": build_implementation_result_schema()["properties"]["blockers"],
    },
}


@dataclass
class _Snapshot:
    digests: dict[str, str]
    contents: dict[str, bytes]


def _is_skipped(relative: Path) -> bool:
    return any(
        part in SKIPPED_DIRECTORIES or part.startswith(SKIPPED_PREFIXES)
        for part in relative.parts
    )


def take_snapshot(root: Path) -> _Snapshot:
    digests: dict[str, str] = {}
    contents: dict[str, bytes] = {}

    for directory, dirnames, filenames in os.walk(root):
        relative_dir = Path(directory).relative_to(root)
        dirnames[:] = [
            name for name in dirnames if not _is_skipped(relative_dir / name)
        ]

        for name in filenames:
            relative = relative_dir / name

            if _is_skipped(relative):
                continue

            path = root / relative

            try:
                if path.stat().st_size > MAX_COLLECTED_FILE_BYTES:
                    continue
                data = path.read_bytes()
            except OSError:
                continue

            key = relative.as_posix()
            digests[key] = hashlib.sha256(data).hexdigest()
            contents[key] = data

    return _Snapshot(digests, contents)


def collect_changes(root: Path, before: _Snapshot) -> dict[str, str]:
    """Text files created or modified since `before`."""

    after = take_snapshot(root)
    changes: dict[str, str] = {}

    for path, digest in after.digests.items():
        if before.digests.get(path) == digest:
            continue

        try:
            changes[path] = after.contents[path].decode("utf-8")
        except UnicodeDecodeError:
            continue

    return changes


def restore_snapshot(root: Path, before: _Snapshot) -> None:
    """Put every tracked file back as it was; remove the files created."""

    after = take_snapshot(root)

    for path in after.digests:
        if path not in before.digests:
            try:
                (root / path).unlink()
            except OSError:
                pass

    for path, data in before.contents.items():
        target = root / path

        if after.digests.get(path) == before.digests[path]:
            continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError:
            pass


def extract_json(text: str) -> str:
    """The JSON object in a model answer, fences and prose around it removed."""

    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)

    if fenced:
        return fenced.group(1)

    start, end = text.find("{"), text.rfind("}")

    if start != -1 and end > start:
        return text[start:end + 1]

    return text


def _plain_error(message: str) -> ProviderExecutionError:
    lowered = message.lower()

    if any(marker in lowered for marker in AUTH_MARKERS):
        return ProviderExecutionError(
            kind=ProviderErrorKind.PERMANENT_REQUEST,
            message=(
                "Claude Code is not signed in on this computer. Open a "
                f"terminal, run `claude`, sign in, then relaunch. ({message})"
            ),
        )

    if any(marker in lowered for marker in LIMIT_MARKERS):
        return ProviderExecutionError(
            kind=ProviderErrorKind.RATE_LIMITED,
            message=(
                "Claude usage limit reached for now. Wait until it resets, "
                f"then relaunch. ({message})"
            ),
        )

    return ProviderExecutionError(
        kind=ProviderErrorKind.UNKNOWN,
        message=f"Claude Code failed: {message}",
    )


class ClaudeCodeProvider(OpenAIProvider):
    """Every Factory call answered by the local Claude Code CLI."""

    def __init__(
        self,
        model: str | None = None,
        settings: dict[str, Any] | None = None,
        models: dict[str, str] | None = None,
        executable: str | None = None,
    ) -> None:
        # Deliberately not calling OpenAIProvider.__init__: no API key and
        # no OpenAI client. Only its prompts and parsers are reused.
        self.model = (model or "").strip()
        self.settings = settings or {}
        self.models = {
            role: name.strip()
            for role, name in (models or {}).items()
            if isinstance(role, str) and isinstance(name, str) and name.strip()
        }
        self._agent_name = None
        self.executable = executable or self.settings.get("claude_executable") or shutil.which("claude")
        self.project_root: Path | None = None

        if not self.executable:
            raise ValueError(
                "Claude Code is not installed or not on the PATH. Install it "
                "(https://code.claude.com) and sign in with `claude`."
            )

    # -- plumbing -------------------------------------------------------------

    def _timeout(self, key: str, default: int) -> int:
        value = self.settings.get(key)
        return int(value) if isinstance(value, (int, float)) and value > 0 else default

    def _invoke(
        self,
        prompt: str,
        *,
        label: str | None,
        cwd: Path,
        tools: str,
        permission_mode: str,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> str:
        args = [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--permission-mode",
            permission_mode,
            "--allowedTools",
            tools,
        ]

        if tools == READ_ONLY_TOOLS:
            args += ["--disallowedTools", "Bash,Edit,Write,NotebookEdit"]

        model = self.model_for(label)

        if model:
            args += ["--model", model]

        outcome = run_process(
            args,
            cwd=cwd,
            env=env,
            timeout=timeout,
            input_text=prompt,
            timeout_note=f"\n[Factory: Claude Code did not answer within {timeout} seconds.]",
        )

        if outcome.timed_out:
            raise ProviderExecutionError(
                kind=ProviderErrorKind.NETWORK,
                message=f"Claude Code did not finish within {timeout} seconds.",
            )

        try:
            payload = json.loads(outcome.stdout.strip().splitlines()[-1]) if outcome.stdout.strip() else {}
        except (ValueError, IndexError):
            payload = {}

        if not isinstance(payload, dict) or "result" not in payload:
            detail = (outcome.stderr or outcome.stdout or "no output").strip()[-800:]
            raise _plain_error(detail)

        if payload.get("is_error") or outcome.returncode != 0:
            raise _plain_error(str(payload.get("result") or outcome.stderr).strip()[-800:])

        return str(payload.get("result") or "")

    def _cwd(self) -> Path:
        return self.project_root if self.project_root and self.project_root.is_dir() else Path.cwd()

    # -- every non-code call ----------------------------------------------------

    def _request(
        self,
        prompt: str,
        *,
        label: str | None,
        schema_name: str | None = None,
        schema: dict | None = None,
        max_output_tokens: Any = None,
        retry_max_output_tokens: Any = None,
    ) -> str:
        if schema is not None:
            prompt = (
                prompt
                + "\n\n## Answer Format\n"
                "Do not modify any file. Answer with ONE JSON object and "
                "nothing else (no prose, no code fence), valid against this "
                f"JSON Schema named {schema_name}:\n"
                + json.dumps(schema, ensure_ascii=False)
            )
        else:
            prompt += "\n\nDo not modify any file. Answer with the requested content only."

        text = self._invoke(
            prompt,
            label=label,
            cwd=self._cwd(),
            tools=READ_ONLY_TOOLS,
            permission_mode="dontAsk",
            timeout=self._timeout("call_timeout_seconds", DEFAULT_CALL_TIMEOUT_SECONDS),
        )

        if schema is not None:
            text = extract_json(text)

        if not text.strip():
            raise ProviderExecutionError(
                kind=ProviderErrorKind.UNKNOWN,
                message="Claude Code returned an empty answer.",
            )

        return text

    # -- implementation -----------------------------------------------------------

    def implement_in_workspace(self, prompt: str, project_root: Path) -> ImplementationResult:
        """Let Claude Code implement and test one task in the project, then
        hand the changed files to the Factory's transaction."""

        project_root = Path(project_root)
        before = take_snapshot(project_root)
        env = {**os.environ, **active_project_environment()}

        instructions = (
            prompt
            + "\n\n## How You Work Here\n"
            "You are running inside the project directory with file and "
            "shell tools. Do the task for real:\n"
            "1. Read the existing files you need instead of guessing them.\n"
            "2. Write or edit the files of this task.\n"
            "3. Install dependencies if the task needs new ones (declare them "
            "in the manifest first).\n"
            "4. Run the task's targeted test commands yourself, read the "
            "output, fix the code or the test, and run them again until they "
            "pass. Run the tests of earlier tasks you touched as well.\n"
            "5. Never modify anything under .factory/ and never delete files.\n"
            "6. Do not start servers that keep running, and close database "
            "pools in tests so every test command exits.\n"
            "When you are done, answer with ONE JSON object and nothing else "
            "(no prose, no code fence), valid against this JSON Schema: "
            + json.dumps(IMPLEMENTATION_FINAL_SCHEMA, ensure_ascii=False)
            + "\n`tests` lists the exact commands, run from the project root, "
            "that validate this task and that passed for you. `blockers` is "
            "empty unless something only a human can provide is missing."
        )

        try:
            text = self._invoke(
                instructions,
                label="implementation",
                cwd=project_root,
                tools=IMPLEMENTATION_TOOLS,
                permission_mode="acceptEdits",
                timeout=self._timeout(
                    "implementation_timeout_seconds",
                    DEFAULT_IMPLEMENTATION_TIMEOUT_SECONDS,
                ),
                env=env,
            )
            changes = collect_changes(project_root, before)
        finally:
            # The Factory applies the changes itself, in a transaction.
            restore_snapshot(project_root, before)

        try:
            final = json.loads(extract_json(text))
        except ValueError as error:
            raise ProviderExecutionError(
                kind=ProviderErrorKind.UNKNOWN,
                message="Claude Code did not end with the JSON summary of the task.",
            ) from error

        if not isinstance(final, dict):
            final = {}

        if not str(final.get("task_id") or "").strip():
            match = re.search(r"^Task ID: (.+)$", prompt, re.MULTILINE)
            final["task_id"] = match.group(1).strip() if match else ""

        final["files"] = [
            {"path": path, "content": content, "operation": "write"}
            for path, content in sorted(changes.items())
        ]
        final.setdefault("setup_commands", [])
        final.setdefault("tests", [])
        final.setdefault("blockers", [])

        return self._parse_implementation_result(json.dumps(final, ensure_ascii=False))
