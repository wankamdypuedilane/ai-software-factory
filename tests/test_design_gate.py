import pytest

from ai_factory.design_gate import get_design_gate


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
