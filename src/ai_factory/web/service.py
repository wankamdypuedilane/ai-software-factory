"""What the web interface can do, without any HTTP.

Every action goes through the same engine functions as the CLI (approvals,
resume, retry, rework, run_workflow), so the interface cannot reach a state
the CLI could not. This module only translates the engine's state into
"what does the human need to do now" and back.
"""

from __future__ import annotations

import json
import os
import re
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ai_factory.approval_runtime import apply_approval
from ai_factory.approvals import APPROVAL_BY_AGENT
from ai_factory.context_builder import load_agent_input
from ai_factory.orchestrator import AGENT_ORDER, get_next_agent
from ai_factory.project import (
    get_product_input_path,
    initialize_project,
    project_slug,
)
from ai_factory.provider_factory import create_provider
from ai_factory.providers import ModelProvider
from ai_factory.replan_guard import (
    BUDGETED_AGENTS,
    RESETTABLE_STATUSES,
    is_budget_exhausted,
    reset_replan_budget,
)
from ai_factory.resume import resume_agent_with_input
from ai_factory.rework import (
    REWORK_ITEM_FIELDS,
    get_rework_items,
    request_rework,
)
from ai_factory.runtime import run_workflow
from ai_factory.state import load_state, save_state
from ai_factory.technology_gate import approve_technology_gate
from ai_factory.technology_selection import (
    apply_approved_technology_to_config,
)
from ai_factory.transitions import retry_agent


STEP_LABELS = {
    "product": "Cadrage",
    "ux_ui": "Design",
    "architect": "Architecture",
    "developer": "Développement",
    "qa": "Tests (QA)",
    "security": "Sécurité",
    "devops": "Livraison (DevOps)",
    "sre": "Fiabilité (SRE)",
}

GATE_BY_AGENT = {
    "ux_ui": "design_gate",
    "architect": "technology_gate",
    "developer": "development_gate",
    "qa": "qa_gate",
    "security": "security_gate",
    "devops": "devops_gate",
    "sre": "sre_gate",
}

PROFILE_INSTRUCTIONS = {
    "novice": (
        "The project owner does not write code. Choose technologies "
        "yourself, prefer simple and widely used options, explain every "
        "decision in plain language without jargon, and always offer a "
        "recommended answer."
    ),
    "developer": (
        "The project owner is a developer. Ask for their technology "
        "preferences when it matters and use precise technical language."
    ),
}

# Files and folders the interface never lists or serves.
HIDDEN_PARTS = {
    ".factory",
    ".git",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".venv",
}

MAX_FILE_BYTES = 400_000


class ServiceError(ValueError):
    """An action the human asked for is not possible right now."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(name: str) -> str:
    try:
        return project_slug(name)
    except ValueError as error:
        raise ServiceError(
            "Le nom du projet doit contenir des lettres ou des chiffres."
        ) from error


@dataclass
class Job:
    """One background run of the workflow for a project."""

    running: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)


ProviderFactory = Callable[[dict[str, Any]], ModelProvider]


class FactoryService:
    """Projects in one workspace folder, driven by the Factory engine."""

    def __init__(
        self,
        workspace: Path,
        provider_factory: ProviderFactory = create_provider,
        settings_path: Path | None = None,
        run_in_background: bool = True,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.provider_factory = provider_factory
        self.settings_path = (
            settings_path
            if settings_path is not None
            else Path.home() / ".ai-factory" / "settings.json"
        )
        self.run_in_background = run_in_background
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._apply_saved_api_key()

    # -- settings -----------------------------------------------------------

    def _read_settings(self) -> dict[str, Any]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

        return data if isinstance(data, dict) else {}

    def _apply_saved_api_key(self) -> None:
        key = self._read_settings().get("openai_api_key")

        if isinstance(key, str) and key.strip() and not os.environ.get(
            "OPENAI_API_KEY"
        ):
            os.environ["OPENAI_API_KEY"] = key.strip()

    def get_settings(self) -> dict[str, Any]:
        settings = self._read_settings()

        return {
            "provider": settings.get("provider", "openai"),
            "model": settings.get("model", "gpt-6-luna"),
            "api_key_set": bool(os.environ.get("OPENAI_API_KEY")),
            "workspace": str(self.workspace),
        }

    def save_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        settings = self._read_settings()

        provider = values.get("provider")

        if provider is not None:
            if provider not in {"openai", "mock"}:
                raise ServiceError("Fournisseur inconnu.")
            settings["provider"] = provider

        model = values.get("model")

        if isinstance(model, str) and model.strip():
            settings["model"] = model.strip()

        key = values.get("openai_api_key")

        if isinstance(key, str) and key.strip():
            settings["openai_api_key"] = key.strip()
            os.environ["OPENAI_API_KEY"] = key.strip()

        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(settings, indent=2),
            encoding="utf-8",
        )

        try:
            os.chmod(self.settings_path, 0o600)
        except OSError:
            pass

        return self.get_settings()

    # -- projects -----------------------------------------------------------

    def _project_root(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", project_id or ""):
            raise ServiceError("Projet introuvable.")

        root = self.workspace / project_id

        if not (root / ".factory" / "state.yaml").is_file():
            raise ServiceError("Projet introuvable.")

        return root

    def _paths(self, project_id: str) -> tuple[Path, Path, Path]:
        root = self._project_root(project_id)

        return (
            root,
            root / ".factory" / "state.yaml",
            root / ".factory" / "project.yaml",
        )

    def list_projects(self) -> list[dict[str, Any]]:
        projects = []

        for child in sorted(self.workspace.iterdir()):
            state_path = child / ".factory" / "state.yaml"

            if not state_path.is_file():
                continue

            try:
                state = load_state(state_path)
            except Exception:
                continue

            projects.append(
                {
                    "id": child.name,
                    "name": state.get("project", {}).get("name", child.name),
                    "phase": state.get("project", {}).get("phase"),
                }
            )

        return projects

    def create_project(
        self,
        name: str,
        idea: str,
        profile: str = "novice",
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ServiceError("Donne un nom à ton projet.")

        if not isinstance(idea, str) or len(idea.strip()) < 10:
            raise ServiceError("Décris ton idée en une ou deux phrases.")

        if profile not in PROFILE_INSTRUCTIONS:
            raise ServiceError("Profil inconnu.")

        if (self.workspace / _slug(name)).exists():
            raise ServiceError("Un projet porte déjà ce nom.")

        root = initialize_project(
            project_name=name.strip(),
            target_dir=self.workspace,
        )

        config_path = root / ".factory" / "project.yaml"
        config = load_state(config_path)
        settings = self._read_settings()

        provider = settings.get("provider", "openai")
        config.setdefault("ai", {})
        config["ai"]["provider"] = provider
        config["ai"]["model"] = (
            settings.get("model", "gpt-6-luna")
            if provider == "openai"
            else None
        )
        config["ui"] = {"profile": profile}

        save_state(config_path, config)

        get_product_input_path(root, config).write_text(
            "# Product Input\n\n"
            "## Idea\n\n"
            f"{idea.strip()}\n\n"
            "## Project owner\n\n"
            f"{PROFILE_INSTRUCTIONS[profile]}\n",
            encoding="utf-8",
        )

        self.start_run(root.name)

        return self.project_view(root.name)

    # -- running ------------------------------------------------------------

    def _job(self, project_id: str) -> Job:
        with self._lock:
            return self._jobs.setdefault(project_id, Job())

    def start_run(self, project_id: str) -> None:
        root, _, config_path = self._paths(project_id)
        job = self._job(project_id)

        with self._lock:
            if job.running:
                return

            job.running = True
            job.error = None
            job.started_at = _now()
            job.finished_at = None

        def work() -> None:
            try:
                provider = self.provider_factory(load_state(config_path))
                executions = run_workflow(
                    project_root=root,
                    provider=provider,
                )
                job.log.extend(
                    f"{agent}: {result.status}"
                    for agent, result in executions
                )
            except Exception as error:  # reported to the human, never raised
                job.error = str(error) or error.__class__.__name__
                job.log.append(traceback.format_exc(limit=3))
            finally:
                with self._lock:
                    job.running = False
                    job.finished_at = _now()

        if self.run_in_background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()

    def _ensure_idle(self, project_id: str) -> None:
        if self._job(project_id).running:
            raise ServiceError("Les agents travaillent encore, attends la fin de l'étape.")

    # -- human actions ------------------------------------------------------

    def _append_input(
        self,
        root: Path,
        config: dict[str, Any],
        agent_name: str,
        heading: str,
        lines: list[str],
    ) -> None:
        existing = load_agent_input(root, config, agent_name) or ""
        path = get_product_input_path(root, config).with_name(f"{agent_name}.md")

        if agent_name == "product":
            path = get_product_input_path(root, config)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            existing.rstrip()
            + ("\n\n" if existing.strip() else "")
            + f"## {heading}\n\n"
            + "\n".join(lines)
            + "\n",
            encoding="utf-8",
        )

    def answer_questions(
        self,
        project_id: str,
        agent_name: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._ensure_idle(project_id)
        root, state_path, config_path = self._paths(project_id)
        state = load_state(state_path)
        config = load_state(config_path)

        agent = state.get("agents", {}).get(agent_name)

        if not isinstance(agent, dict) or agent.get("status") != "BLOCKED":
            raise ServiceError("Cet agent n'attend pas de réponse.")

        lines = []

        for item in answers or []:
            if not isinstance(item, dict):
                continue

            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()

            if question and answer:
                lines.append(f"- {question}\n  Answer: {answer}")

        if not lines:
            raise ServiceError("Réponds au moins à une question.")

        self._append_input(root, config, agent_name, "Answers", lines)

        state = resume_agent_with_input(
            project_root=root,
            state=state,
            project_config=config,
            agent_name=agent_name,
        )
        save_state(state_path, state)

        self.start_run(project_id)

        return self.project_view(project_id)

    def approve_step(
        self,
        project_id: str,
        step: str,
    ) -> dict[str, Any]:
        self._ensure_idle(project_id)
        root, state_path, config_path = self._paths(project_id)
        state = load_state(state_path)

        try:
            if step == "production":
                state = apply_approval(state, "production_deployment", root)
            else:
                if step not in APPROVAL_BY_AGENT:
                    raise ServiceError("Étape inconnue.")

                if step == "architect":
                    gate = state.get("technology_gate", {})

                    if gate.get("status") == "REVIEW_REQUIRED":
                        state = approve_technology_gate(state)
                        config = apply_approved_technology_to_config(
                            config=load_state(config_path),
                            state=state,
                        )
                        save_state(state_path, state)
                        save_state(config_path, config)

                state = apply_approval(
                    state,
                    APPROVAL_BY_AGENT[step],
                    project_root=root,
                )
        except ServiceError:
            raise
        except ValueError as error:
            raise ServiceError(str(error)) from error

        save_state(state_path, state)

        self.start_run(project_id)

        return self.project_view(project_id)

    def request_changes(
        self,
        project_id: str,
        agent_name: str,
        text: str,
    ) -> dict[str, Any]:
        self._ensure_idle(project_id)
        root, state_path, config_path = self._paths(project_id)
        state = load_state(state_path)
        config = load_state(config_path)

        if not isinstance(text, str) or not text.strip():
            raise ServiceError("Décris ce que tu veux changer.")

        if agent_name not in AGENT_ORDER:
            raise ServiceError("Étape inconnue.")

        self._append_input(
            root,
            config,
            agent_name,
            "Requested changes",
            [text.strip()],
        )

        try:
            state = self._reopen(state, agent_name, "web:request-changes")
        except ValueError as error:
            raise ServiceError(str(error)) from error

        save_state(state_path, state)

        self.start_run(project_id)

        return self.project_view(project_id)

    def _reopen(
        self,
        state: dict[str, Any],
        agent_name: str,
        source: str,
    ) -> dict[str, Any]:
        """Put an agent back to READY, reopening an exhausted budget once.

        Reopening a budget already sets the agent READY; retrying it on top
        of that is refused by the engine, so only one of the two applies.
        """

        if agent_name in BUDGETED_AGENTS and is_budget_exhausted(
            state,
            agent_name,
        ) and state.get("agents", {}).get(agent_name, {}).get("status") in RESETTABLE_STATUSES:
            return reset_replan_budget(
                state,
                agent_name,
                source=source,
            )

        if state.get("agents", {}).get(agent_name, {}).get("status") == "READY":
            return state

        return retry_agent(state, agent_name)

    def send_back(
        self,
        project_id: str,
        source: str,
    ) -> dict[str, Any]:
        self._ensure_idle(project_id)
        _, state_path, _ = self._paths(project_id)
        state = load_state(state_path)

        try:
            state = request_rework(state, source)
        except ValueError as error:
            raise ServiceError(str(error)) from error

        save_state(state_path, state)

        self.start_run(project_id)

        return self.project_view(project_id)

    def retry_step(
        self,
        project_id: str,
        agent_name: str,
    ) -> dict[str, Any]:
        self._ensure_idle(project_id)
        _, state_path, _ = self._paths(project_id)
        state = load_state(state_path)

        try:
            state = self._reopen(state, agent_name, "web:retry")
        except ValueError as error:
            raise ServiceError(str(error)) from error

        save_state(state_path, state)

        self.start_run(project_id)

        return self.project_view(project_id)

    # -- reading ------------------------------------------------------------

    def list_files(self, project_id: str) -> list[str]:
        root = self._project_root(project_id)
        files = []

        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)

            if any(part in HIDDEN_PARTS for part in relative.parts):
                continue

            if path.is_file():
                files.append(relative.as_posix())

        return files

    def read_file(self, project_id: str, relative_path: str) -> str:
        root = self._project_root(project_id)

        if not isinstance(relative_path, str) or not relative_path:
            raise ServiceError("Fichier introuvable.")

        path = (root / relative_path).resolve()

        if root.resolve() not in path.parents or not path.is_file():
            raise ServiceError("Fichier introuvable.")

        if any(
            part in HIDDEN_PARTS
            for part in path.relative_to(root.resolve()).parts
        ):
            raise ServiceError("Fichier introuvable.")

        if path.stat().st_size > MAX_FILE_BYTES:
            raise ServiceError("Fichier trop volumineux pour être affiché.")

        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ServiceError("Ce fichier n'est pas du texte.") from error

    def _agent_outputs(
        self,
        state: dict[str, Any],
        agent_name: str,
    ) -> list[str]:
        last_result = (
            state.get("agents", {}).get(agent_name, {}).get("last_result")
            or {}
        )

        paths: list[str] = []

        for key in ("generated_artifacts", "implemented_files"):
            values = last_result.get(key)

            if isinstance(values, list):
                paths.extend(
                    value
                    for value in values
                    if isinstance(value, str)
                )

        return list(dict.fromkeys(paths))

    def _questions(
        self,
        last_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        details = last_result.get("question_details")

        if isinstance(details, list) and details:
            return [
                detail
                for detail in details
                if isinstance(detail, dict) and detail.get("question")
            ]

        return [
            {"question": question, "why": "", "needs_owner_text": True, "options": []}
            for question in last_result.get("questions", []) or []
            if isinstance(question, str) and question.strip()
        ]

    def _gate(self, state: dict[str, Any], agent_name: str) -> dict[str, Any]:
        gate = state.get(GATE_BY_AGENT.get(agent_name, ""), {})

        return gate if isinstance(gate, dict) else {}

    def _review_ready(self, state: dict[str, Any], agent_name: str) -> bool:
        gate = self._gate(state, agent_name)
        status = gate.get("status")

        if agent_name == "architect":
            return status in {"REVIEW_REQUIRED", "APPROVED"}

        if agent_name == "product":
            return True

        return status == "READY_FOR_REVIEW"

    def _steps(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        agents = state.get("agents", {})

        return [
            {
                "agent": name,
                "label": STEP_LABELS[name],
                "status": agents.get(name, {}).get("status", "NOT_STARTED"),
            }
            for name in AGENT_ORDER
        ]

    def _pending(
        self,
        project_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        job = self._job(project_id)

        if job.running:
            agent = get_next_agent(state)

            return {
                "kind": "running",
                "agent": agent,
                "label": STEP_LABELS.get(agent or "", ""),
                "started_at": job.started_at,
            }

        if state.get("project", {}).get("phase") == "completed":
            return {"kind": "completed"}

        agents = state.get("agents", {})

        for name in AGENT_ORDER:
            agent = agents.get(name, {})
            status = agent.get("status")
            last_result = agent.get("last_result") or {}

            if status == "APPROVED":
                continue

            base = {
                "agent": name,
                "label": STEP_LABELS[name],
                "summary": last_result.get("summary", ""),
                "owner_summary": last_result.get("owner_summary") or {},
                "outputs": self._agent_outputs(state, name),
                "error": job.error,
            }

            if status == "BLOCKED":
                questions = self._questions(last_result)

                if questions:
                    return {**base, "kind": "questions", "questions": questions}

                return {
                    **base,
                    "kind": "attention",
                    "reasons": _blocking_reasons(last_result),
                }

            if status == "REVIEW_REQUIRED" and self._review_ready(state, name):
                review = {**base, "kind": "review"}

                if name == "architect":
                    review["technology"] = (
                        state.get("technology_gate", {})
                        .get("proposal", {})
                        .get("components", [])
                    )

                return review

            if status in {"REVIEW_REQUIRED", "FAILED"}:
                items = (
                    get_rework_items(state, name)
                    if name in REWORK_ITEM_FIELDS
                    else []
                )

                return {
                    **base,
                    "kind": "attention",
                    "reasons": list(self._gate(state, name).get("reasons", []) or []),
                    "items": items,
                    "can_send_back": bool(items)
                    and agents.get("developer", {}).get("status") == "APPROVED",
                }

            if status in {"READY", "NOT_STARTED", "IN_PROGRESS"}:
                return {**base, "kind": "ready"}

        production_gate = state.get("production_gate", {})

        if production_gate.get("status") == "READY_FOR_REVIEW":
            return {"kind": "production"}

        return {"kind": "ready", "error": job.error}

    def project_view(self, project_id: str) -> dict[str, Any]:
        root, state_path, config_path = self._paths(project_id)
        state = load_state(state_path)
        config = load_state(config_path)
        job = self._job(project_id)

        return {
            "id": project_id,
            "name": state.get("project", {}).get("name", project_id),
            "phase": state.get("project", {}).get("phase"),
            "profile": (config.get("ui") or {}).get("profile", "novice"),
            "provider": (config.get("ai") or {}).get("provider"),
            "steps": self._steps(state),
            "pending": self._pending(project_id, state),
            "running": job.running,
            "next_agent": get_next_agent(state),
            "files": self.list_files(project_id),
        }


def _blocking_reasons(last_result: dict[str, Any]) -> list[str]:
    """Return what actually stopped the step, most specific first.

    A Developer stop comes from one implementation unit. Its blockers are
    the real cause; the agent-level ones are planning notes, often
    non-blocking, which a real run showed in place of the actual reason.
    """

    reasons: list[str] = []

    for item in last_result.get("implementation_blockers", []) or []:
        if not isinstance(item, dict):
            continue

        for blocker in item.get("blockers", []) or []:
            if isinstance(blocker, dict) and blocker.get("blocking", True):
                message = str(blocker.get("message", "")).strip()

                if message:
                    task = item.get("task_id")
                    reasons.append(f"{task} : {message}" if task else message)

    if reasons:
        return reasons

    blockers = [
        blocker
        for blocker in last_result.get("blockers", []) or []
        if isinstance(blocker, dict) and str(blocker.get("message", "")).strip()
    ]
    blocking = [blocker for blocker in blockers if blocker.get("blocking", True)]

    return [str(blocker["message"]).strip() for blocker in blocking or blockers]
