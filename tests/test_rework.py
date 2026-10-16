from pathlib import Path

import pytest

from ai_factory.cli import main
from ai_factory.context_builder import build_agent_context
from ai_factory.implementation_batch import _known_files
from ai_factory.implementation_prompt import build_implementation_prompt
from ai_factory.implementation_request import ImplementationTask
from ai_factory.prompt_builder import build_agent_prompt
from ai_factory.rework import (
    ReworkError,
    get_open_rework,
    mark_rework_addressed,
    request_rework,
)
from ai_factory.state import load_state, save_state


QA_DEFECT = {
    "id": "QA-01",
    "title": "next_id 0 is accepted",
    "severity": "Medium",
    "related_story": "US-01",
    "expected": "IDs start at 1",
    "actual": "Added todo 0.",
}


def _gate() -> dict:
    return {
        "status": "APPROVED",
        "reasons": [],
        "human_approval": True,
    }


def _state_after_failed_qa() -> dict:
    return {
        "project": {"id": "todo", "name": "Todo", "phase": "qa"},
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {
                "status": "APPROVED",
                "last_result": {
                    "implemented_files": [
                        "todo/storage.py",
                        "tests/test_storage.py",
                    ],
                    "implementation_results": [
                        {"task_id": "todo-storage", "blockers": []},
                    ],
                    "replan_count": 2,
                    "repeated_failures": 1,
                    "failure_signature": "test_failed|x",
                },
            },
            "qa": {
                "status": "FAILED",
                "last_result": {
                    "qa_defects": [QA_DEFECT],
                    "qa_retry_count": 2,
                    "qa_repeated_failures": 1,
                    "qa_failure_signature": "qa|x",
                },
            },
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "approvals": {
            "product_scope": True,
            "design": True,
            "architecture": True,
            "development": True,
            "qa": False,
            "security": False,
            "devops": False,
            "sre": False,
            "production_deployment": False,
        },
        "development_gate": _gate(),
        "qa_gate": {
            "status": "NOT_READY",
            "reasons": ["qa_failed"],
            "human_approval": False,
        },
        "security_gate": {"status": "NOT_STARTED", "reasons": [], "human_approval": False},
        "devops_gate": {"status": "NOT_STARTED", "reasons": [], "human_approval": False},
        "sre_gate": {"status": "NOT_STARTED", "reasons": [], "human_approval": False},
        "production_gate": {"status": "NOT_STARTED", "reasons": [], "human_approval": False},
    }


def test_rework_reopens_development_with_the_qa_defects() -> None:
    state = request_rework(_state_after_failed_qa(), "qa")

    assert state["agents"]["developer"]["status"] == "READY"
    assert state["approvals"]["development"] is False
    assert state["development_gate"]["status"] == "NOT_STARTED"
    assert state["development_gate"]["human_approval"] is False

    assert state["agents"]["qa"]["status"] == "NOT_STARTED"
    assert state["qa_gate"]["status"] == "NOT_STARTED"

    developer_result = state["agents"]["developer"]["last_result"]
    assert developer_result["implementation_results"] == []
    assert developer_result["replan_count"] == 0
    assert developer_result["implemented_files"] == [
        "todo/storage.py",
        "tests/test_storage.py",
    ]

    assert state["agents"]["qa"]["last_result"]["qa_retry_count"] == 0

    rework = get_open_rework(state)
    assert rework["source"] == "qa"
    assert rework["items"] == [QA_DEFECT]
    assert {entry["agent"] for entry in rework["budget_resets"]} == {
        "developer",
        "qa",
    }

    assert state["rework_history"][0]["item_ids"] == ["QA-01"]
    assert state["project"]["phase"] == "implementation"


def test_rework_from_security_also_reopens_an_approved_qa() -> None:
    state = _state_after_failed_qa()
    state["agents"]["qa"]["status"] = "APPROVED"
    state["approvals"]["qa"] = True
    state["qa_gate"] = _gate()
    state["agents"]["security"] = {
        "status": "FAILED",
        "last_result": {
            "security_findings": [{"id": "SEC-01", "title": "Path traversal"}],
        },
    }

    state = request_rework(state, "security")

    assert state["agents"]["qa"]["status"] == "NOT_STARTED"
    assert state["approvals"]["qa"] is False
    assert state["qa_gate"]["status"] == "NOT_STARTED"
    assert state["agents"]["security"]["status"] == "NOT_STARTED"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda state: state["agents"]["developer"].update(status="READY"),
            "retry developer",
        ),
        (
            lambda state: state["agents"]["qa"]["last_result"].update(qa_defects=[]),
            "no item",
        ),
        (
            lambda state: state["agents"]["qa"].update(status="APPROVED"),
            "requires it to be",
        ),
    ],
)
def test_rework_is_refused_outside_its_preconditions(mutate, message) -> None:
    state = _state_after_failed_qa()
    mutate(state)

    with pytest.raises(ReworkError, match=message):
        request_rework(state, "qa")


def test_rework_rejects_an_unknown_source() -> None:
    with pytest.raises(ReworkError, match="only be requested"):
        request_rework(_state_after_failed_qa(), "product")


def test_mark_rework_addressed_closes_the_open_request() -> None:
    state = request_rework(_state_after_failed_qa(), "qa")

    state = mark_rework_addressed(state)

    assert get_open_rework(state) is None
    assert state["rework"]["status"] == "ADDRESSED"


def test_developer_prompts_carry_the_rework_request() -> None:
    state = request_rework(_state_after_failed_qa(), "qa")
    rework = get_open_rework(state)

    planning = build_agent_prompt(
        {
            "agent_name": "developer",
            "contract": "Developer contract",
            "project": {},
            "state": {},
            "rework_request": rework,
        }
    )
    implementation = build_implementation_prompt(
        task=ImplementationTask(
            agent_name="developer",
            id="fix-qa-01",
            title="Fix QA-01",
            purpose="Reject next_id 0.",
        ),
        context={"rework_request": rework},
    )

    for prompt in (planning, implementation):
        assert "## Rework Request" in prompt
        assert "QA-01" in prompt
        assert "IDs start at 1" in prompt


def test_build_agent_context_adds_the_open_rework_for_the_developer(
    tmp_path: Path,
) -> None:
    state = request_rework(_state_after_failed_qa(), "qa")
    save_state(tmp_path / ".factory" / "state.yaml", state)
    save_state(
        tmp_path / ".factory" / "project.yaml",
        {"project": {"name": "Todo"}, "context": {"agents": {}}},
    )

    developer_context = build_agent_context(tmp_path, "developer")
    qa_context = build_agent_context(tmp_path, "qa")

    assert developer_context["rework_request"]["source"] == "qa"
    assert "rework_request" not in qa_context


def test_known_files_combine_previous_cycles_and_this_batch(
    tmp_path: Path,
) -> None:
    known = _known_files(
        project_root=tmp_path,
        context={
            "state": {
                "agents": {
                    "developer": {
                        "last_result": {
                            "implemented_files": ["todo/storage.py"],
                        },
                    },
                },
            },
        },
        written_files=[
            tmp_path / "todo" / "service.py",
            tmp_path / "todo" / "storage.py",
        ],
    )

    assert known == ["todo/storage.py", "todo/service.py"]


def _run_cli(monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr("sys.argv", ["ai-factory", *args])
    main()
    return capsys.readouterr().out


def test_mock_project_goes_through_rework_and_back_to_qa(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    _run_cli(monkeypatch, capsys, "init", "Rework App")

    project_root = tmp_path / "rework-app"
    monkeypatch.chdir(project_root)

    for command in (
        ("run-workflow",),
        ("approve", "product_scope"),
        ("run-workflow",),
        ("approve", "design"),
        ("run-workflow",),
        ("technology", "approve"),
        ("approve", "architecture"),
        ("run-workflow",),
        ("approve", "development"),
        ("run-workflow",),
    ):
        _run_cli(monkeypatch, capsys, *command)

    # QA found a defect in the approved code.
    state_path = project_root / ".factory" / "state.yaml"
    state = load_state(state_path)
    state["agents"]["qa"]["status"] = "FAILED"
    state["agents"]["qa"]["last_result"]["qa_defects"] = [QA_DEFECT]
    save_state(state_path, state)

    output = _run_cli(monkeypatch, capsys, "rework", "qa")

    assert "Sent 1 item(s) from 'qa' back to the Developer" in output
    assert "QA-01" in output

    output = _run_cli(monkeypatch, capsys, "run-workflow")

    assert "Agent: developer" in output
    state = load_state(state_path)
    assert state["rework"]["status"] == "ADDRESSED"
    assert state["development_gate"]["status"] == "READY_FOR_REVIEW"

    _run_cli(monkeypatch, capsys, "approve", "development")
    output = _run_cli(monkeypatch, capsys, "run-workflow")

    assert "Agent: qa" in output
    assert "QA Gate status: READY_FOR_REVIEW" in output
