from pathlib import Path

from ai_factory.context_builder import build_agent_context
from ai_factory.state import save_state


def test_build_agent_context_returns_required_data(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "technology": {
                "selection_mode": "recommend",
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="architect",
    )

    assert context["agent_name"] == "architect"
    assert isinstance(context["contract"], str)
    assert context["contract"].strip() != ""
    assert context["project"]["project"]["name"] == "Test Project"
    assert context["state"]["agents"]["architect"]["status"] == "READY"


def test_build_agent_context_loads_configured_artifacts(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    artifact_path = tmp_path / "knowledge" / "requirements.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "# Requirements\n\nTest requirement.",
        encoding="utf-8",
    )

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "technology": {
                "selection_mode": "recommend",
            },
            "context": {
                "agents": {
                    "architect": [
                        "knowledge/requirements.md",
                    ]
                }
            },
        },
    )

    context = build_agent_context(
        project_root=tmp_path,
        agent_name="architect",
    )

    assert "knowledge/requirements.md" in context["artifacts"]
    assert "Test requirement." in context["artifacts"][
        "knowledge/requirements.md"
    ]


def test_build_agent_context_rejects_missing_artifact(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / ".factory"

    save_state(
        factory_dir / "state.yaml",
        {
            "project": {
                "name": "Test Project",
            },
            "agents": {
                "architect": {
                    "status": "READY",
                }
            },
        },
    )

    save_state(
        factory_dir / "project.yaml",
        {
            "schema_version": 1,
            "project": {
                "name": "Test Project",
                "type": "test",
            },
            "context": {
                "agents": {
                    "architect": [
                        "knowledge/missing.md",
                    ]
                }
            },
        },
    )

    try:
        build_agent_context(
            project_root=tmp_path,
            agent_name="architect",
        )

        assert False, "Expected FileNotFoundError"

    except FileNotFoundError:
        pass
