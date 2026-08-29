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
