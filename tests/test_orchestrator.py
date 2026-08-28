from ai_factory.orchestrator import get_next_agent


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