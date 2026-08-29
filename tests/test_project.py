from pathlib import Path

import yaml

from ai_factory.project import initialize_project
from ai_factory.state import load_state


def test_initialize_project_creates_factory_state(tmp_path: Path) -> None:
    project_root = initialize_project(
        project_name="RideFlow",
        target_dir=tmp_path,
    )

    state_path = project_root / ".factory" / "state.yaml"

    assert project_root.exists()
    assert state_path.exists()


def test_initialize_project_uses_normalized_project_id(tmp_path: Path) -> None:
    project_root = initialize_project(
        project_name="Ride Flow",
        target_dir=tmp_path,
    )

    assert project_root.name == "ride-flow"


def test_initialize_project_fails_if_project_exists(tmp_path: Path) -> None:
    initialize_project(
        project_name="RideFlow",
        target_dir=tmp_path,
    )

    try:
        initialize_project(
            project_name="RideFlow",
            target_dir=tmp_path,
        )

        assert False, "Expected FileExistsError"

    except FileExistsError:
        pass


def test_initial_state_is_valid_yaml(tmp_path: Path) -> None:
    project_root = initialize_project(
        project_name="RideFlow",
        target_dir=tmp_path,
    )

    state_path = project_root / ".factory" / "state.yaml"

    with state_path.open("r", encoding="utf-8") as file:
        state = yaml.safe_load(file)

    assert state["project"]["id"] == "rideflow"
    assert state["project"]["name"] == "RideFlow"
    assert state["factory_version"] == "1.0"
    assert state["project"]["phase"] == "discovery"
    assert state["agents"]["product"]["status"] == "READY"
    assert "design_gate" in state
    assert "design_gate" not in state["approvals"]
    assert state["design_gate"]["status"] == "NOT_STARTED"
    assert state["design_gate"]["groups"] == {}
    assert state["design_gate"]["external_blockers"] == []
    assert state["design_gate"]["human_approval"] is False
    assert "technology_gate" in state
    assert state["technology_gate"]["status"] == "NOT_STARTED"
    assert state["technology_gate"]["human_approval"] is False
    assert state["technology_gate"]["proposal"] == {}


def test_initialize_project_creates_project_configuration(tmp_path):
    project_root = initialize_project(
        project_name="Test Project",
        target_dir=tmp_path,
    )

    config_path = project_root / ".factory" / "project.yaml"

    assert config_path.exists()

    config = load_state(config_path)

    assert config["schema_version"] == 1
    assert config["project"]["name"] == "Test Project"
    assert config["capabilities"]["ui"] is True
    assert config["design"]["enabled"] is True
    assert config["design"]["groups"] == {}
    assert config["artifacts"]["ux_ui"] == []
    assert config["technology"]["selection_mode"] == "recommend"
    assert config["technology"]["constraints"] == {}
    assert config["technology"]["selected"]["frontend"] == {}
    assert config["technology"]["selected"]["backend"] == {}
    assert config["technology"]["selected"]["database"] == {}
    assert config["technology"]["selected"]["mobile"] == {}
    assert config["technology"]["selected"]["infrastructure"] == {}
    assert config["technology"]["selected"]["ci_cd"] == {}
    assert config["technology"]["selected"]["observability"] == {}
    assert config["ai"]["provider"] == "mock"
    assert config["ai"]["model"] is None
    assert config["ai"]["settings"]["temperature"] is None
    assert config["ai"]["settings"]["max_output_tokens"] is None
