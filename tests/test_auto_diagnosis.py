from pathlib import Path

import pytest

from ai_factory.auto_diagnosis import (
    AUTO_MARKER,
    HISTORY_FIELD,
    MAX_AUTO_DIAGNOSES_PER_TASK,
    build_diagnosis_prompt,
    coerce_diagnosis,
    try_auto_diagnosis,
)
from ai_factory.providers import MockProvider
from ai_factory.replan_guard import NonConvergingImplementationError
from ai_factory.state import load_state, save_state
from ai_factory.web.service import FactoryService


BOOKING_SERVICE = """export function createBookingService(
  serviceRepository: ServiceRepository,
  bookingRepository: BookingRepository,
  notificationOutboxRepository: NotificationOutboxRepository,
  options: { salonEmail: string }
): BookingService {}
"""

FAILED_TEST = """import { importTypeScript } from "./helpers/import-typescript.mjs";
const { createBookingService } = await importTypeScript(new URL("../src/server/bookings/BookingService.ts", import.meta.url));
createBookingService(services, schedule, bookings, outbox, "salon@example.test");
"""


class Recorder(MockProvider):
    def __init__(self, answer):
        super().__init__()
        self.answer = answer
        self.prompts: list[str] = []

    def diagnose(self, prompt):
        self.prompts.append(prompt)
        return self.answer


def _stuck_project(tmp_path: Path) -> Path:
    service = FactoryService(
        workspace=tmp_path / "projects",
        provider_factory=lambda config: MockProvider(),
        settings_path=tmp_path / "settings.json",
        run_in_background=False,
    )
    service.save_settings({"provider": "mock"})
    service.create_project("Salon", "Une idée suffisamment longue.", "novice")

    for step in ("product", "ux_ui", "architect"):
        service.approve_step("salon", step)

    root = tmp_path / "projects" / "salon"
    (root / "src" / "server" / "bookings").mkdir(parents=True)
    (root / "src" / "server" / "bookings" / "BookingService.ts").write_text(BOOKING_SERVICE, encoding="utf-8")
    (root / "tests" / "helpers").mkdir(parents=True)
    (root / "tests" / "helpers" / "import-typescript.mjs").write_text(
        "export async function importTypeScript(sourceUrl) {}", encoding="utf-8"
    )
    attempt = root / ".factory" / "failed-transactions" / "RS-MVP-008" / "files" / "tests"
    attempt.mkdir(parents=True)
    (attempt / "concurrency.test.mjs").write_text(FAILED_TEST, encoding="utf-8")
    (attempt.parent.parent / "generated-artifacts.txt").write_text("", encoding="utf-8")

    state_path = root / ".factory" / "state.yaml"
    state = load_state(state_path)
    developer = state["agents"]["developer"]
    developer["status"] = "FAILED"
    developer["last_result"].update(
        {
            "failed_task_id": "RS-MVP-008",
            "replan_count": 2,
            "repeated_failures": 1,
            "failure_signature": "test_failed|npm test -- tests/concurrency.test.mjs",
            "implementation_requests": [
                {"id": "RS-MVP-008", "title": "Bloquer un jour de congé", "purpose": "Refuser les réservations."}
            ],
            "test_results": [
                {
                    "command": "npm test -- tests/concurrency.test.mjs",
                    "returncode": 1,
                    "stdout": "not ok 1\n  error: \"L'adresse e-mail du salon n'est pas configurée.\"",
                    "stderr": "",
                }
            ],
        }
    )
    save_state(state_path, state)
    return root


FIX = {
    "cause": "Le test appelle createBookingService avec une mauvaise signature.",
    "instruction": "Appelle createBookingService(services, bookings, outbox, { salonEmail }).",
    "needs_human": False,
    "question": "",
}


def test_prompt_carries_the_evidence_an_expert_reads(tmp_path: Path) -> None:
    root = _stuck_project(tmp_path)
    prompt = build_diagnosis_prompt(root, load_state(root / ".factory" / "state.yaml"), "")

    assert "RS-MVP-008 Bloquer un jour de congé" in prompt
    assert "L'adresse e-mail du salon n'est pas configurée." in prompt
    assert "### tests/concurrency.test.mjs" in prompt  # the failed attempt
    assert "### src/server/bookings/BookingService.ts" in prompt  # the file it calls
    assert "options: { salonEmail: string })" in prompt  # the export index signature


def test_a_diagnosis_becomes_an_instruction_and_reopens_the_budget(tmp_path: Path) -> None:
    root = _stuck_project(tmp_path)
    provider = Recorder(FIX)

    assert try_auto_diagnosis(root, provider) is True

    developer_input = (root / "knowledge" / "inputs" / "developer.md").read_text(encoding="utf-8")
    assert AUTO_MARKER in developer_input
    assert "{ salonEmail }" in developer_input

    developer = load_state(root / ".factory" / "state.yaml")["agents"]["developer"]
    assert developer["status"] == "READY"
    assert developer["last_result"]["repeated_failures"] == 0
    assert developer["replan_budget_resets"][-1]["source"] == "auto:diagnosis"
    assert developer[HISTORY_FIELD][-1]["cause"] == FIX["cause"]


def test_diagnosis_is_bounded_per_task(tmp_path: Path) -> None:
    root = _stuck_project(tmp_path)
    state_path = root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["developer"][HISTORY_FIELD] = [
        {"task_id": "RS-MVP-008", "cause": "x"} for _ in range(MAX_AUTO_DIAGNOSES_PER_TASK)
    ]
    save_state(state_path, state)
    provider = Recorder(FIX)

    assert try_auto_diagnosis(root, provider) is False
    assert provider.prompts == []


def test_a_cause_that_needs_the_owner_stops_with_a_plain_question(tmp_path: Path) -> None:
    root = _stuck_project(tmp_path)
    provider = Recorder(
        {
            "cause": "La base de données de test est injoignable.",
            "instruction": "",
            "needs_human": True,
            "question": "PostgreSQL est-il bien démarré sur ton ordinateur ?",
        }
    )

    assert try_auto_diagnosis(root, provider) is False

    developer = load_state(root / ".factory" / "state.yaml")["agents"]["developer"]
    assert developer["status"] == "FAILED"
    assert developer[HISTORY_FIELD][-1]["needs_human"] is True
    assert not (root / "knowledge" / "inputs" / "developer.md").exists()


def test_providers_without_diagnosis_are_left_alone(tmp_path: Path) -> None:
    root = _stuck_project(tmp_path)

    class Plain:
        pass

    assert try_auto_diagnosis(root, Plain()) is False


@pytest.mark.parametrize(
    "value",
    [None, "text", {"cause": "", "instruction": "x", "needs_human": False}, {"cause": "c", "instruction": "", "needs_human": False}],
)
def test_unusable_diagnoses_are_refused(value) -> None:
    assert coerce_diagnosis(value) is None


def test_run_workflow_diagnoses_then_continues(tmp_path: Path, monkeypatch) -> None:
    from ai_factory import runtime

    root = _stuck_project(tmp_path)
    calls = {"count": 0}

    def fake_next_agent(project_root, provider):
        calls["count"] += 1
        state = load_state(project_root / ".factory" / "state.yaml")

        if state["agents"]["developer"]["last_result"].get("repeated_failures"):
            raise NonConvergingImplementationError("NON_CONVERGING_IMPLEMENTATION: stuck")

        state["agents"]["developer"]["status"] = "REVIEW_REQUIRED"
        save_state(project_root / ".factory" / "state.yaml", state)
        return "developer", "ok"

    monkeypatch.setattr(runtime, "run_next_agent", fake_next_agent)

    runtime.run_workflow(root, Recorder(FIX))

    assert calls["count"] == 2
    assert load_state(root / ".factory" / "state.yaml")["agents"]["developer"]["status"] == "REVIEW_REQUIRED"


def test_stack_traces_lead_to_the_typescript_source(tmp_path: Path) -> None:
    from ai_factory.auto_diagnosis import _paths_in_output

    (tmp_path / "src" / "server").mkdir(parents=True)
    (tmp_path / "src" / "server" / "bookingsRoute.ts").write_text("export {}", encoding="utf-8")
    output = (
        "createBookingsRoute (file:///C:/Users/x/AppData/Local/Temp/tx/workspace/"
        ".test-modules-V7Pdug/src/server/bookingsRoute.mjs:25:47)\n"
        "location: 'C:\\\\Users\\\\x\\\\workspace\\\\src\\\\server\\\\bookingsRoute.ts:1:1'"
    )

    assert _paths_in_output(tmp_path, [output]) == ["src/server/bookingsRoute.ts"]
