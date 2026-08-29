import pytest

from ai_factory.design_gate import get_design_gate, is_design_gate_ready


def test_get_design_gate_returns_design_gate() -> None:
    state = {
        "design_gate": {
            "status": "PARTIAL",
            "passenger_screens_approved": 5,
            "passenger_screens_total": 7,
            "driver_screens_approved": 0,
            "driver_screens_total": 7,
            "figma_blocked": True,
            "human_approval": False,
        }
    }

    result = get_design_gate(state)

    assert result["status"] == "PARTIAL"
    assert result["passenger_screens_approved"] == 5
    assert result["figma_blocked"] is True


def test_get_design_gate_rejects_missing_gate() -> None:
    with pytest.raises(ValueError):
        get_design_gate({})


def test_design_gate_not_ready_when_designs_are_incomplete() -> None:
    state = {
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
        }
    }

    assert is_design_gate_ready(state) is False


def test_design_gate_ready_when_all_designs_are_complete() -> None:
    state = {
        "design_gate": {
            "status": "READY_FOR_REVIEW",
            "groups": {
                "passenger": {
                    "approved": 7,
                    "total": 7,
                },
                "driver": {
                    "approved": 7,
                    "total": 7,
                },
            },
            "external_blockers": [],
            "human_approval": False,
        }
    }

    assert is_design_gate_ready(state) is True
