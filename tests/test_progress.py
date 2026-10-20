from pathlib import Path

from ai_factory.implementation_request import ImplementationTask
from ai_factory.progress import ProgressRecorder, read_progress
from ai_factory.providers import MockProvider
from ai_factory.web.service import FactoryService


def _task(task_id: str) -> ImplementationTask:
    return ImplementationTask(agent_name="developer", id=task_id, title=f"Titre {task_id}", purpose="p")


def test_progress_records_the_unit_at_work_and_the_finished_ones(tmp_path: Path) -> None:
    tasks = [_task("A"), _task("B"), _task("C")]
    progress = ProgressRecorder(tmp_path, "developer", tasks)

    progress.start(0, tasks[0])
    progress.finish(tasks[0], "done")
    progress.start(1, tasks[1])

    data = read_progress(tmp_path)
    assert data["total"] == 3
    assert [task["id"] for task in data["done"]] == ["A"]
    assert data["current"]["id"] == "B" and data["current"]["index"] == 2


def test_running_view_shows_the_progress_of_this_run(tmp_path: Path) -> None:
    service = FactoryService(
        workspace=tmp_path / "projects",
        provider_factory=lambda config: MockProvider(),
        settings_path=tmp_path / "settings.json",
        run_in_background=False,
    )
    service.save_settings({"provider": "mock"})
    service.create_project("Busy", "Une idée suffisamment longue.", "novice")
    job = service._job("busy")
    job.running = True
    job.started_at = "2000-01-01T00:00:00+00:00"
    tasks = [_task("A"), _task("B")]
    progress = ProgressRecorder(tmp_path / "projects" / "busy", "developer", tasks)
    progress.start(0, tasks[0])

    pending = service.project_view("busy")["pending"]

    assert pending["kind"] == "running"
    assert pending["progress"]["total"] == 2
    assert pending["progress"]["current"]["title"] == "Titre A"


def test_progress_of_an_earlier_run_is_not_shown(tmp_path: Path) -> None:
    service = FactoryService(
        workspace=tmp_path / "projects",
        provider_factory=lambda config: MockProvider(),
        settings_path=tmp_path / "settings.json",
        run_in_background=False,
    )
    service.save_settings({"provider": "mock"})
    service.create_project("Old", "Une idée suffisamment longue.", "novice")
    ProgressRecorder(tmp_path / "projects" / "old", "developer", [_task("A")])
    job = service._job("old")
    job.running = True
    job.started_at = "2999-01-01T00:00:00+00:00"

    assert "progress" not in service.project_view("old")["pending"]
