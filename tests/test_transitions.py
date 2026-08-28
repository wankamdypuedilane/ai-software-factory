import pytest

from ai_factory.transitions import set_agent_status


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