from ai_factory.phases import (
    get_project_phase,
)


def test_project_phase_is_discovery_when_product_is_not_approved() -> None:
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
        },
    }

    assert get_project_phase(state) == "discovery"


def test_project_phase_is_design_after_product_approval() -> None:
    state = {
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "READY"},
            "architect": {"status": "NOT_STARTED"},
            "developer": {"status": "NOT_STARTED"},
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
    }

    assert get_project_phase(state) == "design"


def test_project_phase_is_implementation_after_architecture_approval() -> None:
    state = {
        "agents": {
            "product": {"status": "APPROVED"},
            "ux_ui": {"status": "APPROVED"},
            "architect": {"status": "APPROVED"},
            "developer": {"status": "READY"},
            "qa": {"status": "NOT_STARTED"},
            "security": {"status": "NOT_STARTED"},
            "devops": {"status": "NOT_STARTED"},
            "sre": {"status": "NOT_STARTED"},
        },
    }

    assert get_project_phase(state) == "implementation"


def test_project_phase_is_sre_when_sre_is_not_approved() -> None:
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
    }

    assert get_project_phase(state) == "sre"


def test_project_phase_is_production_after_all_agents_are_approved() -> None:
    state = {
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
        },
    }

    assert get_project_phase(state) == "production"
