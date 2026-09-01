from ai_factory.orchestrator import (
    activate_next_agent,
    get_execution_blocker,
    get_next_agent,
)


def test_get_next_agent_returns_product_when_ready() -> None:
    state = {
        "agents": {
            "product": {"status": "READY"},
            "ux_ui": {"status": "NOT_STARTED"},
            "architect": {"status": "NOT_STARTED"},
            "developer": {"status": "NOT_STARTED"},
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        }
    }

    assert get_next_agent(state) == "product"


def test_get_next_agent_returns_failed_agent_for_retry() -> None:
    state = {
        "agents": {
            "product": {"status": "COMPLETED"},
            "ux_ui": {"status": "COMPLETED"},
            "architect": {"status": "COMPLETED"},
            "developer": {"status": "COMPLETED"},
            "qa": {"status": "FAILED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        }
    }

    assert get_next_agent(state) == "qa"


def test_get_next_agent_stops_when_review_is_required() -> None:
    state = {
        "agents": {
            "product": {"status": "REVIEW_REQUIRED"},
            "ux_ui": {"status": "NOT_STARTED"},
            "architect": {"status": "NOT_STARTED"},
            "developer": {"status": "NOT_STARTED"},
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        }
    }

    assert get_next_agent(state) is None


def test_get_execution_blocker_reports_design_gate_details() -> None:
    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            },
            "ux_ui": {
                "status": "REVIEW_REQUIRED",
            },
            "architect": {
                "status": "NOT_STARTED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
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

    blocker = get_execution_blocker(state)

    assert blocker is not None
    assert "UX/UI is waiting for Design Gate completion." in blocker
    assert "Design Gate status: PARTIAL" in blocker
    assert "Passenger: 5/7" in blocker
    assert "Driver: 0/7" in blocker
    assert "External blockers: figma" in blocker


def test_get_execution_blocker_reports_blocked_agent() -> None:
    state = {
        "agents": {
            "product": {
                "status": "BLOCKED",
            }
        }
    }

    blocker = get_execution_blocker(state)

    assert blocker == "Agent 'product' is blocked."


def test_activate_next_agent_moves_next_agent_to_ready() -> None:
    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            },
            "ux_ui": {
                "status": "NOT_STARTED",
            },
            "architect": {
                "status": "NOT_STARTED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        }
    }

    result = activate_next_agent(
        state,
        "product",
    )

    assert result["agents"]["ux_ui"]["status"] == "READY"


def test_activate_next_agent_does_not_override_existing_status() -> None:
    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            },
            "ux_ui": {
                "status": "BLOCKED",
            },
            "architect": {
                "status": "NOT_STARTED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        }
    }

    result = activate_next_agent(
        state,
        "product",
    )

    assert result["agents"]["ux_ui"]["status"] == "BLOCKED"


def test_activate_next_agent_returns_state_for_last_agent() -> None:
    state = {
        "agents": {
            "sre": {
                "status": "APPROVED",
            }
        }
    }

    result = activate_next_agent(
        state,
        "sre",
    )

    assert result == state


def test_get_execution_blocker_reports_technology_gate_details() -> None:
    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            },
            "ux_ui": {
                "status": "APPROVED",
            },
            "architect": {
                "status": "REVIEW_REQUIRED",
            },
            "developer": {
                "status": "NOT_STARTED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "technology_gate": {
            "status": "REVIEW_REQUIRED",
            "human_approval": False,
            "proposal": {
                "components": {
                    "backend": {
                        "technology": "Python",
                        "rationale": "Suitable for the project.",
                    },
                },
            },
        },
    }

    blocker = get_execution_blocker(
        state
    )

    assert blocker is not None

    assert (
        "Architect is waiting for Technology Gate completion."
        in blocker
    )

    assert (
        "Technology Gate status: REVIEW_REQUIRED"
        in blocker
    )

    assert (
        "Human approval: pending"
        in blocker
    )


def test_get_execution_blocker_reports_development_gate_details() -> None:
    state = {
        "agents": {
            "product": {
                "status": "APPROVED",
            },
            "ux_ui": {
                "status": "APPROVED",
            },
            "architect": {
                "status": "APPROVED",
            },
            "developer": {
                "status": "REVIEW_REQUIRED",
            },
            "qa": {
                "status": "NOT_STARTED",
            },
            "security": {
                "status": "NOT_STARTED",
            },
            "devops": {
                "status": "NOT_STARTED",
            },
            "sre": {
                "status": "NOT_STARTED",
            },
        },
        "development_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    blocker = get_execution_blocker(
        state
    )

    assert blocker is not None

    assert (
        "Developer is waiting for Development Gate completion."
        in blocker
    )

    assert (
        "Development Gate status: READY_FOR_REVIEW"
        in blocker
    )

    assert (
        "Human approval: pending"
        in blocker
    )


def test_get_execution_blocker_reports_qa_gate_details() -> None:
    state = {
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "REVIEW_REQUIRED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "qa_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    blocker = get_execution_blocker(state)

    assert blocker is not None
    assert "QA is waiting for QA Gate completion." in blocker
    assert "QA Gate status: READY_FOR_REVIEW" in blocker
    assert "Human approval: pending" in blocker


def test_get_execution_blocker_reports_security_gate_details() -> None:
    state = {
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "REVIEW_REQUIRED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "security_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    blocker = get_execution_blocker(state)

    assert blocker is not None
    assert "Security is waiting for Security Gate completion." in blocker
    assert "Security Gate status: READY_FOR_REVIEW" in blocker
    assert "Human approval: pending" in blocker


def test_get_execution_blocker_reports_devops_gate_details() -> None:
    state = {
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "APPROVED"},
            "devops": {"status": "REVIEW_REQUIRED"},
            "sre": {"status": "NOT_STARTED"},
        },
        "devops_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    blocker = get_execution_blocker(state)

    assert blocker is not None
    assert "DevOps is waiting for DevOps Gate completion." in blocker
    assert "DevOps Gate status: READY_FOR_REVIEW" in blocker
    assert "Human approval: pending" in blocker


def test_get_execution_blocker_reports_sre_gate_details() -> None:
    state = {
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "APPROVED"},
            "devops": {"status": "APPROVED"},
            "sre": {"status": "REVIEW_REQUIRED"},
        },
        "sre_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    blocker = get_execution_blocker(state)

    assert blocker is not None
    assert "SRE is waiting for SRE Gate completion." in blocker
    assert "SRE Gate status: READY_FOR_REVIEW" in blocker
    assert "Human approval: pending" in blocker


def test_get_execution_blocker_reports_production_gate_details() -> None:
    state = {
        "project": {
            "name": "Test Project",
            "phase": "production",
        },
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "APPROVED"},
            "qa": {"status": "APPROVED"},
            "security": {"status": "APPROVED"},
            "devops": {"status": "APPROVED"},
            "sre": {"status": "APPROVED"},
        },
        "production_gate": {
            "status": "READY_FOR_REVIEW",
            "reasons": [],
            "human_approval": False,
        },
    }

    blocker = get_execution_blocker(
        state
    )

    assert blocker is not None

    assert (
        "Production deployment is waiting for Production Gate completion."
        in blocker
    )

    assert (
        "Production Gate status: READY_FOR_REVIEW"
        in blocker
    )

    assert (
        "Human approval: pending"
        in blocker
    )
