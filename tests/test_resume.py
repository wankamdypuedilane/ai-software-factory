from pathlib import Path

import pytest

from ai_factory.resume import resume_agent_with_input


def test_resume_agent_with_input_moves_blocked_agent_to_ready(
    tmp_path: Path,
) -> None:
    input_path = (
        tmp_path
        / "knowledge"
        / "inputs"
        / "product.md"
    )

    input_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_path.write_text(
        "# Product Input\n\nAdditional context.",
        encoding="utf-8",
    )

    state = {
        "agents": {
            "product": {
                "status": "BLOCKED",
            }
        }
    }

    project_config = {
        "inputs": {
            "directory": "knowledge/inputs",
        }
    }

    result = resume_agent_with_input(
        project_root=tmp_path,
        state=state,
        project_config=project_config,
        agent_name="product",
    )

    assert result["agents"]["product"]["status"] == "READY"


def test_resume_agent_with_input_rejects_missing_input(
    tmp_path: Path,
) -> None:
    state = {
        "agents": {
            "product": {
                "status": "BLOCKED",
            }
        }
    }

    project_config = {
        "inputs": {
            "directory": "knowledge/inputs",
        }
    }

    with pytest.raises(
        ValueError,
        match="Human input is required",
    ):
        resume_agent_with_input(
            project_root=tmp_path,
            state=state,
            project_config=project_config,
            agent_name="product",
        )


def test_resume_agent_with_input_rejects_empty_input(
    tmp_path: Path,
) -> None:
    input_path = (
        tmp_path
        / "knowledge"
        / "inputs"
        / "product.md"
    )

    input_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    input_path.write_text(
        "   ",
        encoding="utf-8",
    )

    state = {
        "agents": {
            "product": {
                "status": "BLOCKED",
            }
        }
    }

    project_config = {
        "inputs": {
            "directory": "knowledge/inputs",
        }
    }

    with pytest.raises(
        ValueError,
        match="Human input is required",
    ):
        resume_agent_with_input(
            project_root=tmp_path,
            state=state,
            project_config=project_config,
            agent_name="product",
        )
