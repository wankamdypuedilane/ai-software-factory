import os
from pathlib import Path

import pytest

from ai_factory.providers import MockProvider
from ai_factory.state import load_state, save_state
from ai_factory.web.service import FactoryService, ServiceError


def _service(tmp_path: Path, ask_questions: bool = True) -> FactoryService:
    service = FactoryService(
        workspace=tmp_path / "projects",
        provider_factory=lambda config: MockProvider(
            ask_questions=ask_questions,
        ),
        settings_path=tmp_path / "settings.json",
        run_in_background=False,
    )
    service.save_settings({"provider": "mock"})
    return service


def test_full_project_through_the_service(tmp_path: Path) -> None:
    service = _service(tmp_path)

    view = service.create_project(
        "Salon Booking",
        "Une application de réservation pour mon salon de coiffure.",
        "novice",
    )

    assert view["id"] == "salon-booking"
    assert view["profile"] == "novice"
    assert view["pending"]["kind"] == "questions"
    question = view["pending"]["questions"][0]
    assert question["options"][0]["recommended"] is True

    product_input = (
        tmp_path / "projects" / "salon-booking" / "knowledge" / "inputs" / "product.md"
    ).read_text(encoding="utf-8")
    assert "salon de coiffure" in product_input
    assert "does not write code" in product_input

    view = service.answer_questions(
        "salon-booking",
        "product",
        [
            {
                "question": question["question"],
                "answer": question["options"][0]["label"],
            }
        ],
    )

    assert view["pending"] == {
        **view["pending"],
        "kind": "review",
        "agent": "product",
    }

    for step in ("product", "ux_ui", "architect", "developer", "qa", "security", "devops", "sre"):
        assert view["pending"]["kind"] == "review", (step, view["pending"])
        assert view["pending"]["agent"] == step
        view = service.approve_step("salon-booking", step)

    assert view["pending"]["kind"] == "production"
    view = service.approve_step("salon-booking", "production")

    assert view["pending"]["kind"] == "completed"
    assert view["phase"] == "completed"
    assert "src/mock_app.py" in view["files"]
    assert all(step["status"] == "APPROVED" for step in view["steps"])


def test_review_lists_the_documents_of_the_step(tmp_path: Path) -> None:
    service = _service(tmp_path, ask_questions=False)
    service.create_project("Docs", "Une petite application de notes.", "developer")
    view = service.approve_step("docs", "product")

    assert view["pending"]["agent"] == "ux_ui"
    assert "design/ux-ui/screen-specs.md" in view["pending"]["outputs"]
    assert service.read_file("docs", "design/ux-ui/screen-specs.md").strip()


def test_request_changes_records_them_and_reruns_the_step(tmp_path: Path) -> None:
    service = _service(tmp_path, ask_questions=False)
    service.create_project("Notes", "Une petite application de notes.", "novice")

    view = service.request_changes("notes", "product", "Ajoute un mode hors ligne.")

    product_input = (
        tmp_path / "projects" / "notes" / "knowledge" / "inputs" / "product.md"
    ).read_text(encoding="utf-8")
    assert "## Requested changes" in product_input
    assert "mode hors ligne" in product_input
    assert view["pending"]["kind"] == "review"


def test_send_back_reopens_development(tmp_path: Path) -> None:
    service = _service(tmp_path, ask_questions=False)
    service.create_project("Rework", "Une petite application de notes.", "novice")

    for step in ("product", "ux_ui", "architect", "developer"):
        service.approve_step("rework", step)

    state_path = tmp_path / "projects" / "rework" / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["qa"]["status"] = "FAILED"
    state["agents"]["qa"]["last_result"]["qa_defects"] = [
        {"id": "QA-01", "title": "ID 0 accepted", "severity": "Medium"},
    ]
    save_state(state_path, state)

    view = service.project_view("rework")
    assert view["pending"]["kind"] == "attention"
    assert view["pending"]["can_send_back"] is True

    view = service.send_back("rework", "qa")

    assert view["pending"]["agent"] == "developer"
    assert view["pending"]["kind"] == "review"


def test_files_never_expose_engine_state_or_escape_the_project(tmp_path: Path) -> None:
    service = _service(tmp_path, ask_questions=False)
    service.create_project("Safe", "Une petite application de notes.", "novice")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    assert not any(path.startswith(".factory") for path in service.list_files("safe"))

    for path in ("../../secret.txt", ".factory/state.yaml", "/etc/passwd", ""):
        with pytest.raises(ServiceError):
            service.read_file("safe", path)

    with pytest.raises(ServiceError):
        service.project_view("../projects")


def test_create_project_validates_its_input(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ServiceError):
        service.create_project("", "Une idée suffisamment longue.", "novice")

    with pytest.raises(ServiceError):
        service.create_project("Court", "trop", "novice")

    with pytest.raises(ServiceError):
        service.create_project("Profil", "Une idée suffisamment longue.", "boss")

    service.create_project("Twice", "Une idée suffisamment longue.", "novice")

    with pytest.raises(ServiceError):
        service.create_project("Twice", "Une idée suffisamment longue.", "novice")


def test_settings_store_the_key_privately(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = _service(tmp_path)

    settings = service.save_settings(
        {"provider": "openai", "model": "gpt-6-luna", "openai_api_key": "sk-test"}
    )

    assert settings["api_key_set"] is True
    assert "openai_api_key" not in settings
    if os.name != "nt":  # Windows has no POSIX permission bits
        assert (tmp_path / "settings.json").stat().st_mode & 0o077 == 0


def test_a_failed_run_is_reported_not_raised(tmp_path: Path) -> None:
    def broken(config):
        raise ValueError("OPENAI_API_KEY environment variable is required.")

    service = FactoryService(
        workspace=tmp_path / "projects",
        provider_factory=broken,
        settings_path=tmp_path / "settings.json",
        run_in_background=False,
    )

    view = service.create_project("Broken", "Une idée suffisamment longue.", "novice")

    assert view["running"] is False
    assert "OPENAI_API_KEY" in view["pending"]["error"]


def test_project_name_with_accents_is_reachable(tmp_path: Path) -> None:
    service = _service(tmp_path, ask_questions=False)

    view = service.create_project("Réservations Salon", "Une idée suffisamment longue.", "novice")

    assert view["id"] == "reservations-salon"
    assert view["name"] == "Réservations Salon"


def test_running_view_names_the_working_step(tmp_path: Path) -> None:
    service = _service(tmp_path, ask_questions=False)
    service.create_project("Busy", "Une idée suffisamment longue.", "novice")
    service._job("busy").running = True
    service._job("busy").started_at = "2026-10-16T03:00:00+00:00"

    pending = service.project_view("busy")["pending"]

    assert pending["kind"] == "running"
    assert pending["started_at"] == "2026-10-16T03:00:00+00:00"


@pytest.mark.parametrize("action", ["retry", "changes"])
def test_failed_step_with_exhausted_budget_can_be_reopened(tmp_path: Path, action: str) -> None:
    service = _service(tmp_path, ask_questions=False)
    service.create_project("Stuck", "Une idée suffisamment longue.", "novice")

    for step in ("product", "ux_ui", "architect"):
        service.approve_step("stuck", step)

    state_path = tmp_path / "projects" / "stuck" / ".factory" / "state.yaml"
    state = load_state(state_path)
    developer = state["agents"]["developer"]
    developer["status"] = "FAILED"
    developer["last_result"]["replan_count"] = 3
    developer["last_result"]["repeated_failures"] = 1
    developer["last_result"]["failure_signature"] = "test_failed|npm test"
    save_state(state_path, state)

    if action == "retry":
        view = service.retry_step("stuck", "developer")
    else:
        view = service.request_changes("stuck", "developer", "Return plain objects.")

    assert view["pending"]["agent"] == "developer"
    assert view["pending"]["kind"] == "review"
