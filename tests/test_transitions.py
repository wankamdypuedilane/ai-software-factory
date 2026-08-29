import pytest

from ai_factory.state import save_state
from ai_factory.transitions import retry_agent, resume_agent, set_agent_status


def test_set_agent_status_updates_status() -> None:
    state = {
        "agents": {
            "product": {"status": "READY"},
        }
    }

    updated_state = set_agent_status(
        state,
        "product",
        "IN_PROGRESS",
    )

    assert updated_state["agents"]["product"]["status"] == "IN_PROGRESS"


def test_set_agent_status_rejects_invalid_status() -> None:
    state = {
        "agents": {
            "product": {"status": "READY"},
        }
    }

    with pytest.raises(ValueError):
        set_agent_status(
            state,
            "product",
            "UNKNOWN",
        )


def test_set_agent_status_rejects_unknown_agent() -> None:
    state = {
        "agents": {
            "product": {"status": "READY"},
        }
    }

    with pytest.raises(KeyError):
        set_agent_status(
            state,
            "nonexistent",
            "IN_PROGRESS",
        )


def test_set_agent_status_rejects_forbidden_transition() -> None:
    state = {
        "agents": {
            "product": {"status": "READY"},
        }
    }

    with pytest.raises(ValueError):
        set_agent_status(
            state,
            "product",
            "COMPLETED",
        )


def create_test_project_config(tmp_path, required_artifacts):
    config_path = tmp_path / ".factory" / "project.yaml"

    config = {
        "schema_version": 1,
        "project": {
            "name": "Test Project",
            "type": "test",
        },
        "capabilities": {
            "ui": True,
        },
        "design": {
            "enabled": True,
            "groups": {},
        },
        "artifacts": {
            "ux_ui": required_artifacts,
        },
    }

    save_state(config_path, config)


def test_ux_ui_cannot_request_review_with_missing_artifacts(tmp_path):
    required_files = [
        "knowledge/ux-ui/user-flows.md",
        "knowledge/ux-ui/design-system.md",
    ]

    create_test_project_config(
        tmp_path,
        required_files,
    )

    state = {
        "agents": {
            "ux_ui": {
                "status": "IN_PROGRESS",
            }
        }
    }

    with pytest.raises(ValueError, match="UX/UI artifacts are incomplete"):
        set_agent_status(
            state,
            "ux_ui",
            "REVIEW_REQUIRED",
            project_root=tmp_path,
        )


def test_ux_ui_can_request_review_when_artifacts_exist(tmp_path):
    required_files = [
        "knowledge/ux-ui/user-flows.md",
        "knowledge/ux-ui/screen-inventory.md",
        "knowledge/ux-ui/visual-direction.md",
        "knowledge/ux-ui/design-system.md",
        "knowledge/ux-ui/high-fidelity-brief.md",
        "knowledge/ux-ui/wireframes/passenger-booking.md",
        "knowledge/ux-ui/wireframes/driver-ride.md",
        "knowledge/ux-ui/wireframes/supporting-screens.md",
        "knowledge/ux-ui/high-fidelity/passenger-screens.md",
        "knowledge/ux-ui/high-fidelity/driver-screens.md",
        "knowledge/ux-ui/high-fidelity/component-specs.md",
    ]

    create_test_project_config(
        tmp_path,
        required_files,
    )

    for relative_path in required_files:
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch()

    state = {
        "agents": {
            "ux_ui": {
                "status": "IN_PROGRESS",
            }
        }
    }

    result = set_agent_status(
        state,
        "ux_ui",
        "REVIEW_REQUIRED",
        project_root=tmp_path,
    )

    assert result["agents"]["ux_ui"]["status"] == "REVIEW_REQUIRED"


def test_ux_ui_cannot_be_approved_when_design_gate_is_not_ready() -> None:
    state = {
        "agents": {
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
            }
        },
        "design_gate": {
            "status": "PARTIAL",
            "groups": {
                "passenger": {
                    "approved": 5,
                    "total": 7,
                },
                "driver": {
                    "approved": 0,
                    "total": 7,
                },
            },
            "external_blockers": [
                "figma",
            ],
            "human_approval": False,
        },
    }

    with pytest.raises(
        ValueError,
        match="Design Gate is not ready",
    ):
        set_agent_status(
            state,
            "ux_ui",
            "APPROVED",
        )


def test_architect_approval_requires_technology_gate_when_recommended(
    tmp_path,
) -> None:
    config_path = tmp_path / ".factory" / "project.yaml"

    save_state(
        config_path,
        {
            "technology": {
                "selection_mode": "recommend",
            }
        },
    )

    state = {
        "agents": {
            "architect": {
                "status": "REVIEW_REQUIRED",
            }
        },
        "technology_gate": {
            "status": "REVIEW_REQUIRED",
            "human_approval": False,
            "proposal": {},
        },
    }

    with pytest.raises(
        ValueError,
        match="Technology Gate is not approved",
    ):
        set_agent_status(
            state,
            "architect",
            "APPROVED",
            project_root=tmp_path,
        )


def test_architect_approval_succeeds_when_technology_gate_is_approved(
    tmp_path,
) -> None:
    config_path = tmp_path / ".factory" / "project.yaml"

    save_state(
        config_path,
        {
            "technology": {
                "selection_mode": "recommend",
            }
        },
    )

    state = {
        "agents": {
            "architect": {
                "status": "REVIEW_REQUIRED",
            }
        },
        "technology_gate": {
            "status": "APPROVED",
            "human_approval": True,
            "proposal": {},
        },
    }

    result = set_agent_status(
        state,
        "architect",
        "APPROVED",
        project_root=tmp_path,
    )

    assert result["agents"]["architect"]["status"] == "APPROVED"


def test_architect_approval_does_not_require_gate_in_manual_mode(
    tmp_path,
) -> None:
    config_path = tmp_path / ".factory" / "project.yaml"

    save_state(
        config_path,
        {
            "technology": {
                "selection_mode": "manual",
            }
        },
    )

    state = {
        "agents": {
            "architect": {
                "status": "REVIEW_REQUIRED",
            }
        },
    }

    result = set_agent_status(
        state,
        "architect",
        "APPROVED",
        project_root=tmp_path,
    )

    assert result["agents"]["architect"]["status"] == "APPROVED"


def test_resume_agent_moves_blocked_agent_to_ready() -> None:
    state = {
        "agents": {
            "product": {
                "status": "BLOCKED",
            }
        }
    }

    result = resume_agent(
        state,
        "product",
    )

    assert result["agents"]["product"]["status"] == "READY"


def test_resume_agent_rejects_non_blocked_agent() -> None:
    state = {
        "agents": {
            "product": {
                "status": "READY",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="is not blocked",
    ):
        resume_agent(
            state,
            "product",
        )


def test_resume_agent_rejects_unknown_agent() -> None:
    state = {
        "agents": {}
    }

    with pytest.raises(
        KeyError,
        match="Unknown agent",
    ):
        resume_agent(
            state,
            "unknown",
        )


def test_retry_agent_moves_review_required_to_ready() -> None:
    state = {
        "agents": {
            "product": {
                "status": "REVIEW_REQUIRED",
            }
        }
    }

    result = retry_agent(
        state,
        "product",
    )

    assert result["agents"]["product"]["status"] == "READY"


def test_retry_agent_moves_failed_to_ready() -> None:
    state = {
        "agents": {
            "architect": {
                "status": "FAILED",
            }
        }
    }

    result = retry_agent(
        state,
        "architect",
    )

    assert result["agents"]["architect"]["status"] == "READY"


def test_retry_agent_rejects_invalid_status() -> None:
    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            }
        }
    }

    with pytest.raises(
        ValueError,
        match="cannot be retried",
    ):
        retry_agent(
            state,
            "product",
        )
