from ai_factory.orchestrator import get_next_agent


def test_next_agent_is_product() -> None:
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