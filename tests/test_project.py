from pathlib import Path

import yaml

from ai_factory.project import initialize_project


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
    assert state["design_gate"]["passenger_screens_approved"] == 0
    assert state["design_gate"]["driver_screens_approved"] == 0
    assert state["design_gate"]["figma_blocked"] is False

    
